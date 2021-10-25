import math

import redis
import telebot
from telebot import types
import time
import re

# import json

REDIS_URL = 'redis://:SJqkqqj7NXTXcEWHM6khiao0@ckv40fbvl001j0ub9gbr0g8ry:6379'
TELEBOT_TOKEN = '2083207800:AAFZ1QgWt4mYRv2Aw3gI-i2fmjvvDjZoqH4'
DEPOSIT_LIMIT = -100
LIMIT_MESSAGE = 'У вас исчерпан лимит показов, пожалуйста, свяжитесь с @whitejoe для пополнения баланса'
ADMIN_LIST = ['whitejoe']
ABOUT_LIMIT = 100

CONTENT_TYPES = ["text", "audio", "document", "photo", "sticker", "video", "video_note", "voice", "location", "contact",
                 "new_chat_members", "left_chat_member", "new_chat_title", "new_chat_photo", "delete_chat_photo",
                 "group_chat_created", "supergroup_chat_created", "channel_chat_created", "migrate_to_chat_id",
                 "migrate_from_chat_id", "pinned_message"]


def app():
    redis_url = 'redis://:@localhost:6379'
    # redis_url = REDIS_URL
    bot = telebot.TeleBot(TELEBOT_TOKEN)

    redis_data = redis.from_url(redis_url, db=0)
    drivers = {'about': redis.from_url(redis_url, db=1),
               'radius': redis.from_url(redis_url, db=2),
               'price': redis.from_url(redis_url, db=3),
               'wait': redis.from_url(redis_url, db=4),
               'status': redis.from_url(redis_url, db=5),
               'geo_long': redis.from_url(redis_url, db=6),
               'geo_lat': redis.from_url(redis_url, db=7),
               'impressions': redis.from_url(redis_url, db=8),
               'last_impression': redis.from_url(redis_url, db=9),
               'deposit': redis.from_url(redis_url, db=10)}

    clients = {}
    # redis_data = redis.Redis(host='localhost', port=6379, decode_responses=True)
    if 'count_drivers' not in redis_data:
        redis_data['count_drivers'] = 0
    count_drivers = redis_data['count_drivers']
    if 'count_start' not in redis_data:
        redis_data['count_start'] = 0
    count_start = redis_data['count_start']
    menu_items = ['👍 Поиск машины', '🚕 Я водитель']
    menu_car_items = ['Изменить объявление', 'Изменить радиус', 'Изменить цену за км', 'Выход', "✳️ Поиск пассажира ✳️"]
    menu_stop = "⛔️ Прекратить поиск ⛔️"

    def get_avg(field: str):
        tot = 0
        count = 0
        for k in drivers[field].keys():
            tot += int(drivers[field][k])
            count += 1
        if count == 0:
            return 0
        return int(tot / count)

    def go_start(message):
        username = message.chat.username
        menu_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        menu_keyboard.row(types.KeyboardButton(text=menu_items[0], request_location=True),
                          types.KeyboardButton(text=menu_items[1]))
        menu_message = f"👍 Для поиска машины нажмите “Поиск машины” (или отправьте свои координаты текстом)," \
                       f" бот запросит геопозицию и предложит связаться с " \
                       f"водителями, готовыми приехать за вами. "
        if username in drivers['status'] and int(drivers['status'][username]) >= 0:
            drivers['status'][username] = -1
        if username in drivers['wait'] and int(drivers['wait'][username]) >= 0:
            drivers['wait'][username] = -1
        bot.send_message(message.chat.id, menu_message, reply_markup=menu_keyboard)

    def go_about(message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.username
        drivers['wait'][username] = 0
        bot.send_message(message.chat.id, f"Расскажите немного о себе и машине (не больше {ABOUT_LIMIT} символов),"
                                          f" например: Ильдар. Синяя Хонда. Вожу быстро, но аккуртно.",
                         reply_markup=keyboard)
        return

    def go_radius(message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.username
        drivers['wait'][username] = 1
        avg_km = get_avg('radius')
        bot.send_message(message.chat.id, f"Задайте расстояние в километрах на которое вы готовы поехать за пассажиром."
                                          f"\nСреднее среди водителей: {avg_km}", reply_markup=keyboard)
        return

    def go_price(message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.username
        drivers['wait'][username] = 2
        avg_price = get_avg('price')
        bot.send_message(message.chat.id, f"Напишите сколько денег обычно вы берёте за километр пути (примерно)."
                                          f"\nСреднее среди водителей: {avg_price}", reply_markup=keyboard)
        return

    def get_profile(username):
        info_about = "Поле не заполнено"
        if username in drivers['about']:
            info_about = drivers['about'][username].decode("utf-8")
        info_radius = "Поле не заполнено"
        if username in drivers['radius']:
            info_radius = f"{int(drivers['radius'][username])} км"
        info_price = "Поле не заполнено"
        if username in drivers['price']:
            info_price = f"{int(drivers['price'][username])} руб/км"
        impressions = 0
        if username in drivers['impressions']:
            impressions = int(drivers['impressions'][username])
        balance = 0
        if username in drivers['deposit']:
            balance = int(drivers['deposit'][username])

        info = f"Объявление: {info_about}\nОриентировочная цена: {info_price}\nРадиус поиска: {info_radius}\n" \
               f"Показов сегодгня: {impressions}\nБаланс: {balance}"
        return info

    def go_menu_car(message):
        username = message.chat.username
        menu_car = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        menu_car.row(types.KeyboardButton(text=menu_car_items[0]),
                     types.KeyboardButton(text=menu_car_items[1]))
        menu_car.row(types.KeyboardButton(text=menu_car_items[2]),
                     types.KeyboardButton(text=menu_car_items[3]))
        if username in drivers['about'] and username in drivers['radius'] and username in drivers['price']:
            if username not in drivers['deposit']:
                drivers['deposit'][username] = 0
            drivers['status'][username] = 0
        menu_car_text = "Ваш профиль:\n" + get_profile(username)
        if username in drivers['status'] and int(drivers['status'][username]) == 0:
            if int(drivers['deposit'][username]) >= DEPOSIT_LIMIT:
                menu_car.row(types.KeyboardButton(text=menu_car_items[4], request_location=True))
                menu_car_text = menu_car_text + f"\n🚕 Для поиска пассажира нажмите “Поиск пассажира” (или отправьте" \
                                                f" свои координаты текстом), в указанном вами радиуса бот будет" \
                                                f" показывать ваше оъявление."
            else:
                menu_car_text = menu_car_text + f"\n\n Ваш баланс исчерпан, лимит {DEPOSIT_LIMIT}." \
                                                f" Для пополнения свяжитесь с @whitejoe"
        else:
            menu_car_text = menu_car_text + "\n\n Заполните все поля, что бы начать поиск пассажиров!"
        bot.send_message(message.chat.id, menu_car_text, reply_markup=menu_car)

    def get_distance(long1, lat1, long2, lat2):
        def hav(x):
            return (math.sin(x/2)) ** 2
        planet_radius = 6371  # Радиус текущей планеты (Земля) в КМ, погрешность 0.5%
        long1_rad = math.pi * long1 / 180
        lat1_rad = math.pi * lat1 / 180
        long2_rad = math.pi * long2 / 180
        lat2_rad = math.pi * lat2 / 180
        return 2 * planet_radius * math.asin(math.sqrt(hav(long2_rad - long1_rad) +
                                                math.cos(long1_rad) * math.cos(long1_rad) * hav(lat2_rad - lat1_rad)))


    def go_search(message, location):



        curtime = int(time.time())
        bot.send_message(message.chat.id,
                         f"Тут немного не дописано, но по идее я уже тут предложу тебе список водителей")

    def go_location(message, location):
        username = message.chat.username
        if username in drivers['status'] and int(drivers['status'][username]) >= 0 and\
                int(drivers['deposit'][username]) >= DEPOSIT_LIMIT:
            drivers['status'][username] = 1
            drivers['geo_long'][username] = location['longitude']
            drivers['geo_lat'][username] = location['latitude']
            search_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
            search_keyboard.row(types.KeyboardButton(text=menu_stop))
            bot.send_message(message.chat.id, f"Ну, теперь кури бамбук, пассажиров ещё нет."
                                              f" Но, если ты это читаешь, значит всё работает",
                             reply_markup=search_keyboard)
        else:
            go_search(message, location)
            go_start(message)

    @bot.message_handler(commands=['start'])
    def start_message(message):
        redis_data['count_start'] = int(redis_data['count_start']) + 1
        bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        go_start(message)

    @bot.message_handler(commands=['geo'])
    def geo_message(message):
        try:

            long1 = float(message.text.split(' ')[1])
            lat1 = float(message.text.split(' ')[2])
            long2 = float(message.text.split(' ')[3])
            lat2 = float(message.text.split(' ')[4])
            dist = get_distance(long1, lat1, long2, lat2)
            bot.send_message(message.chat.id, f"Расстояние {dist} км")
        except Exception as e:
            bot.send_message(message.chat.id,
                             f"%USERNAME% какбе ошибсо {e}")
    @bot.message_handler(commands=['deposit'])
    def deposit_message(message):
        if message.chat.username in ADMIN_LIST:
            try:
                username = message.text.split(' ')[1]
                dep = int(message.text.split(' ')[2])
                new_balance = dep + int(drivers['deposit'][username])
                drivers['deposit'][username] = new_balance
                bot.send_message(message.chat.id,
                                 f"Депозит пополнен на {dep}, новый баланс {new_balance}")
            except:
                bot.send_message(message.chat.id,
                                 f"Админ, какбе ошибсо")

    @bot.message_handler(content_types=['text'])
    def message_text(message):
        username = message.chat.username
        if username in drivers['wait'] and int(drivers['wait'][username]) == 0:
            if len(message.text) <= ABOUT_LIMIT:
                drivers['about'][username] = message.text
                drivers['wait'][username] = -1
                go_menu_car(message)
                return
            else:
                bot.send_message(message.chat.id, f"Объявление слишком длинное, ограничение {ABOUT_LIMIT} символов")
                return

        if username in drivers['wait'] and int(drivers['wait'][username]) == 1:
            if str(message.text).isnumeric():
                drivers['radius'][username] = int(message.text)
                drivers['wait'][username] = -1
                go_menu_car(message)
                return
            else:
                bot.send_message(message.chat.id, "Пожалуйста, ведите число")
                return
        if username in drivers['wait'] and int(drivers['wait'][username]) == 2:
            if str(message.text).isnumeric():
                drivers['price'][username] = int(message.text)
                drivers['wait'][username] = -1
                go_menu_car(message)
                return
            else:
                bot.send_message(message.chat.id, "Пожалуйста, ведите число")
                return
        if message.text == menu_items[1]:
            go_menu_car(message)
            return
        if message.text == menu_car_items[0]:
            go_about(message)
            return
        if message.text == menu_car_items[1]:
            go_radius(message)
            return
        if message.text == menu_car_items[2]:
            go_price(message)
            return
        if message.text == menu_car_items[3]:
            drivers['status'][username] = -1
            go_start(message)
            return
        if message.text == menu_stop and int(drivers['status'][username]) == 1:
            go_menu_car(message)
            return

        if re.fullmatch("^(-?\d+(\.\d+)?),\s*(-?\d+(\.\d+)?)$", message.text):
            location = {'longitude': float(message.text.split(',')[0]), 'latitude': float(message.text.split(',')[1])}
            go_location(message, location)
            return
        bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    @bot.message_handler(content_types=['location'])
    def message_geo(message):
        location = {'longitude': message.location.longitude, 'latitude': message.location.latitude}
        go_location(message, location)

    @bot.message_handler(content_types=CONTENT_TYPES)
    def message_any(message):
        bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    bot.polling()


if __name__ == "__main__":
    app()
