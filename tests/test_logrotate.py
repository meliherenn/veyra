import logging

import main
from main import bot_log_handler, rotate_log


def test_a_small_log_is_left_alone(tmp_path):
    path = tmp_path / 'console.log'
    path.write_bytes(b'x' * 10)
    assert rotate_log(path, max_bytes=100) is False
    assert path.read_bytes() == b'x' * 10
    assert not (tmp_path / 'console.log.1').exists()


def test_an_oversized_log_moves_to_a_backup(tmp_path):
    path = tmp_path / 'console.log'
    path.write_bytes(b'x' * 500)
    assert rotate_log(path, max_bytes=100) is True
    assert not path.exists()
    assert (tmp_path / 'console.log.1').read_bytes() == b'x' * 500


def test_only_the_configured_number_of_backups_survives(tmp_path):
    path = tmp_path / 'console.log'
    path.write_bytes(b'new')
    (tmp_path / 'console.log.1').write_bytes(b'old1')
    (tmp_path / 'console.log.2').write_bytes(b'old2')
    rotate_log(path, max_bytes=1, backups=2)
    assert (tmp_path / 'console.log.1').read_bytes() == b'new'
    assert (tmp_path / 'console.log.2').read_bytes() == b'old1'
    assert not (tmp_path / 'console.log.3').exists()


def test_a_missing_log_is_not_an_error(tmp_path):
    assert rotate_log(tmp_path / 'console.log', max_bytes=1) is False


def test_bot_log_handler_rolls_over_instead_of_growing(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'LOG_MAX_BYTES', 64)
    handler = bot_log_handler(tmp_path / 'bot.log')
    logger = logging.getLogger('dwar-test-bot-log')
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        for _ in range(20):
            logger.info('yeterince uzun bir günlük satiri %s', 'x' * 40)
        handler.flush()
        assert (tmp_path / 'bot.log.1').exists()
        assert (tmp_path / 'bot.log').stat().st_size > 0
        assert not (tmp_path / f'bot.log.{main.LOG_BACKUPS + 1}').exists()
    finally:
        handler.close()
        logger.handlers[:] = []
