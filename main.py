import math
import redis
import telebot
from telebot import types
import time
import datetime
import re
import json

REDIS_URL = 'redis://:SJqkqqj7NXTXcEWHM6khiao0@ckv40fbvl001j0ub9gbr0g8ry:6379'
TELEBOT_TOKEN = '2083207800:AAFZ1QgWt4mYRv2Aw3gI-i2fmjvvDjZoqH4'
DEPOSIT_LIMIT = -100
LIMIT_MESSAGE = f"Ваш баланс исчерпан, лимит {DEPOSIT_LIMIT}. Для пополнения свяжитесь с @whitejoe"
ADMIN_LIST = ['whitejoe']
ABOUT_LIMIT = 100
SEARCH_LIVE_TIME = 300
IMPRESSION_COST = 1

CONTENT_TYPES = ["text", "audio", "document", "photo", "sticker", "video", "video_note", "voice", "location", "contact",
                 "new_chat_members", "left_chat_member", "new_chat_title", "new_chat_photo", "delete_chat_photo",
                 "group_chat_created", "supergroup_chat_created", "channel_chat_created", "migrate_to_chat_id",
                 "migrate_from_chat_id", "pinned_message"]


def app():
    redis_url = 'redis://:@localhost:6379'
    # redis_url = REDIS_URL
    bot = telebot.TeleBot(TELEBOT_TOKEN)
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

    clients_search = redis.from_url(redis_url, db=11)

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
                                                f" свои координаты текстом)."
            else:
                menu_car_text = menu_car_text + f"\n\n{LIMIT_MESSAGE}"
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
        res = 2 * planet_radius * math.asin(math.sqrt(hav(long2_rad - long1_rad) + math.cos(long1_rad) *
                                                      math.cos(long1_rad) * hav(lat2_rad - lat1_rad)))
        return res

    def inc_impression(user_driver):
        curtime = int(time.time())
        dt_timestamp = int(datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0)).timestamp())
        if user_driver not in drivers['last_impression'] or int(drivers['last_impression'][user_driver]) < dt_timestamp:
            drivers['impressions'][user_driver] = 0
        drivers['impressions'][user_driver] = int(drivers['impressions'][user_driver]) + 1
        drivers['deposit'][user_driver] = int(drivers['deposit'][user_driver]) - IMPRESSION_COST
        drivers['last_impression'][user_driver] = curtime

    def go_search(message, location):
        username = message.chat.username
        result_list = []
        search_list = []
        result_message = ''
        if username in clients_search:
            search_list_str = clients_search[username].decode("utf-8")
            search_list = json.loads(search_list_str)
        for user_driver_ne in drivers['status'].keys():
            user_driver = user_driver_ne.decode("utf-8")
            if int(drivers['status'][user_driver]) == 1:
                dist = get_distance(location['longitude'], location['latitude'],
                                    float(drivers['geo_long'][user_driver]), float(drivers['geo_lat'][user_driver]))
                if dist < int(drivers['radius'][user_driver]):
                    result_list.append(user_driver)
                    result_message = result_message + f"🚕 {drivers['about'][user_driver].decode('utf-8')}\n" \
                                                      f"Расстояние:{dist:.2f} км\n" \
                                                      f"Примерная цена за км:{int(drivers['price'][user_driver])}\n" \
                                                      f"@{user_driver}\n\n"
                    if user_driver not in search_list:
                        inc_impression(user_driver)
        str_json = json.dumps(result_list)
        clients_search.setex(username, SEARCH_LIVE_TIME, str_json)
        bot.send_message(message.chat.id,
                         f"Найдено водителей {len(result_list)}:\n\n{result_message}")

    def go_location(message, location):
        username = message.chat.username
        if username in drivers['status'] and int(drivers['status'][username]) >= 0 and\
                int(drivers['deposit'][username]) >= DEPOSIT_LIMIT:
            drivers['status'][username] = 1
            drivers['geo_long'][username] = location['longitude']
            drivers['geo_lat'][username] = location['latitude']
            search_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
            search_keyboard.row(types.KeyboardButton(text=menu_stop))
            bot.send_message(message.chat.id, f"Идет поиск, потенциальным пассажирам в указанном вами радиусе бот"
                                              f" будет показывать ваше оъявление. Ждите, вам напишут.",
                             reply_markup=search_keyboard)
        else:
            go_search(message, location)

    @bot.message_handler(commands=['start'])
    def start_message(message):
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
            except Exception as e:
                bot.send_message(message.chat.id,
                                 f"Админ, какбе ошибсо {e}")

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
