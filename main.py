import redis
import telebot
import json

REDIS_URL = 'redis://SJqkqqj7NXTXcEWHM6khiao0:@ckv40fbvl001j0ub9gbr0g8ry:6379'
TELEBOT_TOKEN = '2083207800:AAFZ1QgWt4mYRv2Aw3gI-i2fmjvvDjZoqH4'


def app():
    bot = telebot.TeleBot(TELEBOT_TOKEN)

    redis_data = redis.from_url(REDIS_URL)
    #redis_data = redis.Redis(host='localhost', port=6379, decode_responses=True)
    if 'count_drivers' not in redis_data:
        redis_data['count_drivers'] = 0
    count_drivers = redis_data['count_drivers']
    if 'count_start' not in redis_data:
        redis_data['count_start'] = 0
    count_start = redis_data['count_start']

    if 'drivers' not in redis_data:
        redis_data['drivers'] = json.dumps([]).encode("utf-8")

    @bot.message_handler(commands=['start'])
    def start_message(message):

        redis_data['count_start'] = int(redis_data['count_start']) + 1
        bot.send_message(message.chat.id,
                         f"Бот в разработке, за Вами никто не приедет. Запусков: {int(redis_data['count_start'])}", )

    @bot.message_handler(content_types=['text'])
    def send_text(message):
        drivers = json.loads(redis_data['drivers'])
        bot.send_message(message.chat.id, f"Говорю же, никто не приедет. Водителей {len(drivers)}."
                                          f' Ждите запуска бота')

    bot.polling()


if __name__ == "__main__":
    app()
