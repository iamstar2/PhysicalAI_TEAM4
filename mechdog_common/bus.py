"""paho-mqtt 래퍼. 팀원이 paho-mqtt를 직접 만지지 않도록 감싼다.

사용법:
    bus = MechDogBus(Node.MECHDOG_A)
    bus.connect()
    bus.on(MsgType.DIALOG_RESULT, handler)
    bus.publish(VisionFacePayload(...), session_id=session_id)

브로커 주소는 환경변수 MQTT_HOST / MQTT_PORT 로 설정한다 (기본 localhost:1883).

[보안 모드]
로컬/사내망 데모: MQTT_USER를 설정하지 않으면 인증 없이 그대로 연결한다 (기본값).
외부 네트워크 노출: MQTT_USER / MQTT_PASS 환경변수가 설정되어 있으면 자동으로
username/password 인증을 사용한다. 코드를 바꿀 필요 없이 배포 환경의 .env만
바꾸면 두 모드가 전환된다.
"""

from __future__ import annotations

import os
from typing import Callable

import paho.mqtt.client as mqtt

from .enums import MsgType, Node, NodeState
from .messages import Envelope, PayloadBase, SystemHealthPayload, make_envelope
from .topics import qos_for, retain_for, topic_for, SUBSCRIBE_ALL

Handler = Callable[[Envelope], None]


class MechDogBus:
    def __init__(self, node: Node, client_id: str | None = None, dry_run: bool = False):
        """
        node: 이 프로세스가 대표하는 노드 (컨테이너 이름 = MQTT 클라이언트 ID = node.value 로 통일).
        dry_run: True면 실제 소켓 연결을 하지 않고 publish() 내용을 콘솔에 출력만 한다
                 (mock_publisher.py --dry-run 에서 사용, 브로커 없이 시나리오 확인용).
        """
        self.node = node
        self.dry_run = dry_run
        self._handlers: dict[MsgType, list[Handler]] = {}
        self._client: mqtt.Client | None = None

        if not dry_run:
            self._client = mqtt.Client(client_id=client_id or node.value)

            user = os.environ.get("MQTT_USER")
            password = os.environ.get("MQTT_PASS")
            if user:
                # MQTT_USER가 설정된 경우에만 인증 모드로 전환 (외부 노출 시나리오).
                self._client.username_pw_set(user, password)

            # LWT: 비정상 종료(크래시, 네트워크 끊김) 시 브로커가 대신
            # offline 상태를 발행해준다. 정상 종료 시엔 disconnect()에서
            # 우리가 직접 offline을 보내고 연결을 끊는다.
            offline_env = make_envelope(
                src=node,
                session_id="system",
                payload=SystemHealthPayload(node=node, state=NodeState.OFFLINE),
            )
            self._client.will_set(
                topic_for(MsgType.SYSTEM_HEALTH, node=node),
                payload=offline_env.model_dump_json(),
                qos=qos_for(MsgType.SYSTEM_HEALTH),
                retain=retain_for(MsgType.SYSTEM_HEALTH),
            )

            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message

    def connect(self) -> None:
        if self.dry_run:
            print(f"[dry-run] {self.node.value}: connect() 스킵 (브로커 연결 없음)")
            return
        host = os.environ.get("MQTT_HOST", "localhost")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        self._client.connect(host, port)
        self._client.loop_start()

    def disconnect(self) -> None:
        if self.dry_run or self._client is None:
            return
        online_off = SystemHealthPayload(node=self.node, state=NodeState.OFFLINE)
        self.publish(online_off, session_id="system")
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, payload: PayloadBase, session_id: str) -> Envelope:
        """토픽/QoS/Retain을 자동으로 결정해서 발행. 팀원은 payload와 session_id만 넘기면 된다."""
        env = make_envelope(src=self.node, session_id=session_id, payload=payload)
        msg_type = payload.msg_type
        topic = topic_for(msg_type, node=self.node if msg_type is MsgType.SYSTEM_HEALTH else None)
        qos = qos_for(msg_type)
        retain = retain_for(msg_type)

        if self.dry_run:
            print(f"[dry-run] PUB {topic} (qos={qos}, retain={retain})")
            print(f"          {env.model_dump_json()}")
            return env

        self._client.publish(topic, env.model_dump_json(), qos=qos, retain=retain)
        return env

    def on(self, msg_type: MsgType, handler: Handler) -> None:
        """msg_type 기준으로 핸들러 등록. 여러 개 등록 가능."""
        self._handlers.setdefault(msg_type, []).append(handler)

    def _on_connect(self, client, userdata, flags, rc) -> None:
        client.subscribe(SUBSCRIBE_ALL)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            env = Envelope.model_validate_json(msg.payload)
        except Exception as exc:  # noqa: BLE001 - 잘못된 메시지는 무시하고 로그만 남김
            print(f"[bus] invalid message on {msg.topic}: {exc}")
            return
        for handler in self._handlers.get(env.payload.msg_type, []):
            handler(env)
