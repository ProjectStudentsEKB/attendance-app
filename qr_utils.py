import segno
import time
import io
import base64


def make_lesson_token(lesson_id):
    """Простой токен для QR. Позже заменим на подписанный JWT."""
    return f"{lesson_id}:{int(time.time())}"


def make_qr_base64(data, size=8):
    """Генерирует QR-код и возвращает base64-строку PNG."""
    qr = segno.make(data, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=size, border=2)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def seconds_remaining(period=10):
    """Сколько секунд до обновления QR."""
    return period - (int(time.time()) % period)