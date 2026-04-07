import asyncio
import logging
import random
from collections import deque
from aiogram.types import Message
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand

# ВСТАВЬ СЮДА СВОЙ ТОКЕН ОТ BOTFATHER
BOT_TOKEN = "8691079544:AAFVtzdo3rNx_YWM3K8cVQa-RVvJenbMITg"
ADMIN_ID = 954119969 # 👈 Замени эти цифры на свой реальный Telegram ID

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

games = {}
global_game_counter = 0

# --- ИГРОВЫЕ КЛАССЫ ---

class Player:
    def __init__(self, user_id: int, name: str, number: int):
        self.user_id = user_id
        self.name = name
        self.number = number 
        self.role = None
        self.is_alive = True
        self.is_glued = False 
        self.has_alibi = False
        self.has_nominated = False
        
        # Переменные для ночных способностей
        self.surikens = 0
        self.last_healed = None 
        self.last_alibi = None 
        self.last_man_heal = False 
        self.found_mafia = False 
        self.found_mafia_day = -1
        self.last_rek = None 

class Game:
    def __init__(self, chat_id: int):
        global global_game_counter
        self.chat_id = chat_id
        self.players = {} 
        self.players_by_number = {} 
        self.state = "LOBBY" 
        
        global_game_counter += 1
        self.game_number = global_game_counter
        self.day_count = 0
        self.day_starter_num = 1

        self.nominated = [] 
        self.speech_queue = deque()
        self.defense_queue = deque()
        self.current_speech_task = None
        
        self.voting_queue = deque() 
        self.current_votes = {} 
        self.vote_history = {} # История для команды /voted
        self.balance_players = [] 
        self.revote_count = 0 
        
        self.night_actions = {} 
        self.expected_night_actors = {} 
        self.mafia_team = ["Мафия", "Дон", "Адвокат", "Ниндзя"]
        self.current_preset = []

    def add_player(self, user_id: int, name: str):
        if user_id not in self.players:
            number = len(self.players) + 1
            player = Player(user_id, name, number)
            self.players[user_id] = player
            self.players_by_number[number] = player
            return True
        return False

    def get_alive_players(self):
        return [p for p in self.players.values() if p.is_alive]

    def build_daily_queue(self):
        alive = sorted(self.get_alive_players(), key=lambda p: p.number)
        if not alive: return deque()
        
        start_idx = 0
        for i, p in enumerate(alive):
            if p.number >= self.day_starter_num:
                start_idx = i
                break
                
        self.day_starter_num = alive[start_idx].number
        queue = deque(alive)
        queue.rotate(-start_idx)
        return queue

# --- ПРЕСЕТЫ РОЛЕЙ ---
ROOM_PRESETS = {
    3: [ 
        ["Маньяк с бинтами", "Адвокат", "Шериф"]
    ],
    5: [ 
        ["Мафия", "Шериф", "Доктор", "Мирный житель", "Вор"]
    ],
    6: [
        ["Дон", "Мафия", "Шериф", "Доктор", "Мирный житель", "Мирный житель"],
        ["Дон", "Мафия", "Шериф", "Тула", "Мирный житель", "Мирный житель"],
        ["Маньяк с бинтами", "Мафия", "Мирный житель", "Мирный житель", "Мирный житель", "Мирный житель"]
    ],
    7: [
        ["Двуликий", "Дон", "Шериф", "Доктор", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Двуликий", "Дон", "Шериф", "Тула", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Ниндзя", "Мафия", "Тула", "Шериф", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Мафия", "Маньяк с бинтами", "Вор", "Мирный житель", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Бессмертный", "Шериф", "Мафия", "Ниндзя", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Адвокат", "Мафия", "Маньяк с бинтами", "Шериф", "Бессмертный", "Мирный житель", "Мирный житель"]
    ],
    8: [
        ["Адвокат", "Ниндзя", "Маньяк с бинтами", "Бессмертный", "Доктор", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Адвокат", "Ниндзя", "Маньяк с бинтами", "Бессмертный", "Тула", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Двуликий", "Ниндзя", "Маньяк с бинтами", "Бессмертный", "Доктор", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Вор", "Доктор", "Дон", "Ниндзя", "Мирный житель", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Бессмертный", "Вор", "Ниндзя", "Адвокат", "Мирный житель", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Дон", "Ниндзя", "Шериф", "Бессмертный", "Мирный житель", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Маньяк с бинтами", "Мафия", "Мафия", "Шериф", "Доктор", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Дон", "Мафия", "Шериф", "Тула", "Бессмертный", "Маньяк с бинтами", "Мирный житель", "Мирный житель"]
    ],
    9: [
        ["Мафия", "Мафия", "Мафия", "Маньяк с бинтами", "Шериф", "Бессмертный", "Доктор", "Мирный житель", "Мирный житель"],
        ["Мафия", "Мафия", "Мафия", "Маньяк с бинтами", "Шериф", "Бессмертный", "Тула", "Мирный житель", "Мирный житель"],
        ["Адвокат", "Двуликий", "Ниндзя", "Маньяк с бинтами", "Доктор", "Бессмертный", "Шериф", "Мирный житель", "Мирный житель"],
        ["Адвокат", "Двуликий", "Ниндзя", "Маньяк с бинтами", "Тула", "Бессмертный", "Шериф", "Мирный житель", "Мирный житель"],
        ["Мафия", "Мафия", "Мафия", "Бессмертный", "Вор", "Маньяк с бинтами", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Мафия", "Мафия", "Мафия", "Доктор", "Вор", "Шериф", "Маньяк без бинтов", "Мирный житель", "Мирный житель"]
    ],
    10: [
        ["Мафия", "Мафия", "Мафия", "Маньяк с бинтами", "Шериф", "Бессмертный", "Доктор", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Мафия", "Мафия", "Мафия", "Маньяк с бинтами", "Шериф", "Бессмертный", "Тула", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Адвокат", "Двуликий", "Ниндзя", "Маньяк с бинтами", "Доктор", "Бессмертный", "Шериф", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Адвокат", "Двуликий", "Ниндзя", "Маньяк с бинтами", "Тула", "Бессмертный", "Шериф", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Мафия", "Мафия", "Мафия", "Бессмертный", "Вор", "Маньяк с бинтами", "Мирный житель", "Мирный житель", "Мирный житель", "Мирный житель"],
        ["Мафия", "Мафия", "Мафия", "Доктор", "Вор", "Шериф", "Маньяк без бинтов", "Мирный житель", "Мирный житель", "Мирный житель"]
    ],
    11: [
        ["Дон", "Ниндзя", "Адвокат", "Маньяк с бинтами", "Шериф", "Доктор", "Вор", "Бессмертный", "Мирный житель", "Мирный житель", "Мирный житель"]
    ],
    12: [
        ["Дон", "Ниндзя", "Адвокат", "Мафия", "Маньяк без бинтов", "Шериф", "Доктор", "Тула", "Вор", "Бессмертный", "Мирный житель", "Мирный житель"]
    ],
    13: [
        ["Дон", "Ниндзя", "Адвокат", "Мафия", "Маньяк с бинтами", "Шериф", "Доктор", "Тула", "Вор", "Бессмертный", "Двуликий", "Мирный житель", "Мирный житель"]
    ]
}

# --- ОПИСАНИЯ РОЛЕЙ (ШПАРГАЛКА) ---
ROLE_DESCRIPTIONS = {
    "Мирный житель": "Не имеет ночных способностей. Днем ищет мафию и голосует на суде.",
    "Мафия": "Ночью вместе с командой выбирает жертву для выстрела.",
    "Дон": "Глава <b>МАФИИ</b>. Его голос при стрельбе равен двум. Каждую ночь проверяет одного игрока, ища Шерифа.",
    "Адвокат": "Играет за команду <b>МАФИИ</b>. Ночью дает одному игроку алиби (спасает от дневной казни на следующий день). Не может дать алиби одному и тому же жителю две ночи подряд",
    "Ниндзя": "Играет за команду <b>МАФИИ</b>. Каждую ночь кидает по  одному сюрикену. Для убийства цели нужно два сюрикена. (Лечение сбрасывает сюрикены).",
    "Вор": "Играет за команду <b>МИРНЫХ</b>. Просыпается первым. Заклеивает рот: цель лишается дневной речи и ночного хода. Если заклеит мафию — отменяет выстрел всей команды. Не может заклеить одного и того же жителя две ночи подряд",
    "Доктор": "Играет за команду <b>МИРНЫХ</b>.Ночью спасает одного игрока от убийства. Нельзя лечить одного и того же два раза подряд.",
    "Тула": "Играет за команду <b>МИРНЫХ</b>. Ночью лечит игрока и дает ему алиби на день. Если Тулу убьют, ее клиент умирает вместе с ней (кроме Бессмертного). Не может ходить к одному и тому же жителю два ночи подряд",
    "Шериф": "Играет за команду <b>МИРНЫХ</b>. Ночью проверяет игрока, узнавая мафия он или нет (Маньяк видится мирным всегда, двуликий начинает видеться как мафия со следующей ночи от той, когда он нашел мафию.",
    "Маньяк без бинтов": "Играет <b>САМ ЗА СЕБЯ</b>. Каждую ночь убивает одного игрока. Побеждает, оставшись 1 на 1.",
    "Маньяк с бинтами": "Играет <b>САМ ЗА СЕБЯ</b>. Каждую ночь выбирает: убить игрока ИЛИ вылечить самого себя (нельзя лечить себя 2 ночи подряд).",
    "Двуликий": "Начинает игру за  команду мирных. Ночью ищет мафию (проверка). Как только найдет — узнает их состав и со следующей ночи убивает сам. Для победы <b>ОБЯЗАН ПРИСОЕДИНИТСЯ К КОМАНДЕ МАФИИ</b>",
    "Бессмертный": "Играет за команду <b>МИРНЫХ</b>.Неуязвим ночью: не умирает от выстрелов и сюрикенов. Может уйти только на дневном голосовании."
}

# --- УСЛОВИЯ ПОБЕДЫ ---
async def check_victory(game: Game, chat_id: int) -> bool:
    alive = game.get_alive_players()
    if not alive:
        await bot.send_message(chat_id, "💀 Все игроки погибли! Санек сосет яйца - мафия победила.")
        game.state = "FINISHED"
        return True

    mafia_count = sum(1 for p in alive if p.role in game.mafia_team or (p.role == "Двуликий" and p.found_mafia))
    maniac_count = sum(1 for p in alive if p.role in ["Маньяк без бинтов", "Маньяк с бинтами"])
    town_count = len(alive) - mafia_count - maniac_count

    if maniac_count > 0 and len(alive) == 2:
        await bot.send_message(chat_id, "🔪 Маньяк остался один на один с жертвой! ПОБЕДА МАНЬЯКА!")
        game.state = "FINISHED"
        return True

    if mafia_count == 0 and maniac_count == 0:
        await bot.send_message(chat_id, "🕊 Вся мафия и маньяки уничтожены! ПОБЕДА МИРНОГО ГОРОДА!")
        game.state = "FINISHED"
        return True

    if mafia_count >= (town_count + maniac_count) and maniac_count == 0:
        await bot.send_message(chat_id, "🕴 Мафий за столом стало не меньше, чем мирных! ПОБЕДА МАФИИ!")
        game.state = "FINISHED"
        return True

    return False

# --- ОБРАБОТЧИКИ БАЗОВЫХ КОМАНД ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        await message.answer("Привет! Я бот для Мафии 🕵️‍♂️\nЯ запомнил тебя. Теперь добавь меня в группу с друзьями и напиши там /start_game.")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🛠 <b>Список команд бота:</b>\n\n"
        "<b>Для игроков:</b>\n"
        "🔹 /start — Запустить бота в личных сообщениях\n"
        "🔹 /alive — Показать список живых игроков\n"
        "🔹 /speech — Начать свою речь (когда подошла очередь)\n"
        "🔹 /end_speech — Досрочно закончить речь\n"
        "🔹 /nominate — Выставить игрока на голосование (выдаст кнопки)\n"
        "🔹 /nominated — Посмотреть список выставленных\n"
        "🔹 /vote — Проголосовать на суде (выдаст кнопки)\n"
        "🔹 /voted — Узнать текущие результаты голосования\n"
        "🔹 /description — Описание ролей, играющих за столом\n"
        "🔹 /roles — Набор ролей на эту игру\n\n"
        "<b>Для ведущего (Админа):</b>\n"
        "🔸 /start_game — Открыть регистрацию в чате\n"
        "🔸 /run — Запустить игру (раздать роли)\n"
        "🔸 /start_night — Принудительно начать ночь\n"
        "🔸 /skip_night — Пропустить ночную фазу\n"
    )
    await message.answer(help_text, parse_mode="HTML")

@dp.message(Command("start_game"))
async def cmd_start_game(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔️ Эта команда доступна только создателю игры!")
    chat_id = message.chat.id
    if message.chat.type == "private": return await message.answer("Играть нужно в группе!")
    if chat_id in games and games[chat_id].state not in ["FINISHED"]: return await message.answer("Игра в этом чате уже запущена!")

    games[chat_id] = Game(chat_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✋ Присоединиться", callback_data="join_game")]])
    await message.answer("Регистрация на Мафию открыта! Нажмите кнопку ниже.", reply_markup=kb)

@dp.callback_query(F.data == "join_game")
async def join_game_handler(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    game = games.get(chat_id)
    if not game or game.state != "LOBBY": return await callback.answer("Нет открытого лобби.", show_alert=True)
        
    user = callback.from_user
    if game.add_player(user.id, user.first_name):
        text = f"Зарегистрировано: {len(game.players)} чел.\n" + "\n".join([f"{p.number}. {p.name}" for p in game.players.values()])
        await callback.message.edit_text(text, reply_markup=callback.message.reply_markup)
        await callback.answer("Ты в игре!")
    else:
        await callback.answer("Ты уже зарегистрирован!", show_alert=True)

@dp.message(Command("run"))
async def cmd_run(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔️ Эта команда доступна только создателю игры!")
    chat_id = message.chat.id
    game = games.get(chat_id)
    if not game or game.state != "LOBBY": return
        
    player_count = len(game.players)
    if player_count not in ROOM_PRESETS: return await message.answer(f"Для старта нужно другое количество игроков (сейчас {player_count}).")
        
    roles = random.choice(ROOM_PRESETS[player_count]).copy()
    game.current_preset = roles.copy() 
    random.shuffle(roles)
    
    game.day_starter_num = ((game.game_number - 1) % player_count) + 1
    
    for i, player in enumerate(game.players.values()):
        player.role = roles[i]
        
    mafia_members = [p for p in game.players.values() if p.role in game.mafia_team]
    mafia_text = "\n".join([f"№{p.number} — {p.name} ({p.role})" for p in mafia_members])
    
    for player in game.players.values():
        msg = f"🔢 Твой игровой номер: {player.number}\n🎭 Твоя роль: {player.role}\n\n📖 Что делает твоя роль:\n{ROLE_DESCRIPTIONS[player.role]}"
        if player.role in game.mafia_team:
            msg += f"\n\n🕴 Твоя команда:\n{mafia_text}\n\n*Ночью вы можете общаться с командой прямо здесь, отправляя сообщения боту!*"
            
        try:
            await bot.send_message(player.user_id, msg, parse_mode="HTML")
        except:
            return await message.answer(f"Не удалось отправить роль игроку {player.name}. Он не нажал /start в личке с ботом!")
            
    game.state = "DAY"
    game.day_count = 1
    
    await message.answer(f"🎲 Игра началась!\nНабор ролей: {', '.join(game.current_preset)}")
    
    unique_roles = set(game.current_preset)
    desc_text = "📖 <b>Справка по ролям на эту игру:</b>\n\n"
    for r in unique_roles:
        desc = ROLE_DESCRIPTIONS.get(r, "Описание отсутствует.")
        desc_text += f"🔹 <b>{r}</b>: {desc}\n\n"
        
    await message.answer(desc_text, parse_mode="HTML")
    await start_day_phase(game, chat_id)

@dp.message(Command("alive"))
async def cmd_alive(message: types.Message):
    game = games.get(message.chat.id)
    if not game or game.state in ["LOBBY", "FINISHED"]: 
        return await message.answer("Игра сейчас не идет.")
        
    alive = sorted(game.get_alive_players(), key=lambda p: p.number)
    text = "👤 Живые игроки за столом:\n" + "\n".join([f"№{p.number} — {p.name}" for p in alive])
    await message.answer(text)

@dp.message(Command("description"))
async def cmd_description(message: types.Message):
    game = games.get(message.chat.id)
    if not game or game.state in ["LOBBY", "FINISHED"]: 
        return await message.answer("Игра сейчас не идет.")
        
    unique_roles = set(game.current_preset)
    desc_text = "📖 <b>Справка по ролям в этой игре:</b>\n\n"
    for r in unique_roles:
        desc = ROLE_DESCRIPTIONS.get(r, "Описание отсутствует.")
        desc_text += f"🔹 <b>{r}</b>: {desc}\n\n"
        
    await message.answer(desc_text, parse_mode="HTML")

@dp.message(Command("roles"))
async def cmd_roles(message: types.Message):
    game = games.get(message.chat.id)
    if not game or game.state == "LOBBY": return
    await message.answer(f"📜 Набор ролей в этой игре:\n{', '.join(game.current_preset)}")

# --- ЧАТ МАФИИ (Писать в ЛС боту ночью) ---
@dp.message(F.chat.type == "private")
async def mafia_night_chat(message: types.Message):
    if message.text and message.text.startswith("/"): return
    
    user_id = message.from_user.id
    
    active_game = None
    player = None
    for game in games.values():
        if user_id in game.players and game.state in ["NIGHT_THIEF", "NIGHT"]:
            active_game = game
            player = game.players[user_id]
            break
            
    if not active_game or not player or not player.is_alive: return
    if player.role not in active_game.mafia_team: return
    
    if player.is_glued:
        return await message.answer("🤐 Вы заклеены Вором! Вы не можете говорить в чате мафии этой ночью.")
        
    if not message.text:
        return await message.answer("⚠️ В чат мафии можно отправлять только текстовые сообщения.")

    sent_count = 0
    for other_p in active_game.get_alive_players():
        if other_p.role in active_game.mafia_team and other_p.user_id != user_id:
            try:
                await bot.send_message(
                    other_p.user_id, 
                    f"🥷 [Чат мафии] Игрок №{player.number}: {message.text}"
                )
                sent_count += 1
            except: pass
            
    if sent_count == 0:
        await message.answer("🥷 Вы остались единственным живым мафиози. Вас некому читать.")

# --- ФАЗА ДНЯ: РЕЧИ И ВЫСТАВЛЕНИЯ ---

async def start_day_phase(game: Game, chat_id: int):
    for p in game.players.values():
        p.has_nominated = False
        
    game.revote_count = 0 
    
    if game.day_count > 1:
        alive_nums = sorted([p.number for p in game.get_alive_players()])
        if alive_nums:
            next_starter = alive_nums[0] 
            for num in alive_nums:
                if num > game.day_starter_num:
                    next_starter = num
                    break
            game.day_starter_num = next_starter

    game.nominated = []
    game.speech_queue = game.build_daily_queue()
    if not game.speech_queue: return
        
    first_player = game.speech_queue[0]
    await bot.send_message(chat_id, f"☀️ Наступает День {game.day_count}.\nПервым говорит Игрок №{first_player.number}. Напишите /speech.")

async def next_speaker(game: Game, chat_id: int):
    if game.speech_queue: game.speech_queue.popleft() 
    while game.speech_queue and game.speech_queue[0].is_glued:
        glued_p = game.speech_queue.popleft()
        await bot.send_message(chat_id, f"🤐 Игрок №{glued_p.number} заклеен Вором и пропускает свою речь.")

    if game.speech_queue:
        next_p = game.speech_queue[0]
        await bot.send_message(chat_id, f"🗣 Очередь Игрока №{next_p.number}. Напишите /speech для начала речи.")
    else:
        await bot.send_message(chat_id, "🎙 Все речи окончены!")
        await start_defense_phase(game, chat_id)

async def start_defense_phase(game: Game, chat_id: int):
    if not game.nominated:
        await bot.send_message(chat_id, "Никто не выставлен. Город засыпает...")
        await start_night_phase(game, chat_id)
        return

    game.state = "DEFENSE"
    game.defense_queue = deque([game.players_by_number[num] for num in game.nominated if game.players_by_number[num].is_alive])
    
    if not game.defense_queue:
        await bot.send_message(chat_id, "Все выставленные мертвы. Город засыпает...")
        await start_night_phase(game, chat_id)
        return

    await bot.send_message(chat_id, f"⚖️ Выставлены игроки: {game.nominated}.\nПереходим к оправдательным речам! Первым говорит Игрок №{game.defense_queue[0].number}. Напишите /speech.")


@dp.message(Command("speech"))
async def cmd_speech(message: types.Message):
    game = games.get(message.chat.id)
    if not game: return
    
    player = game.players.get(message.from_user.id)
    if not player: return

    if game.state == "DAY":
        if not game.speech_queue or player.user_id != game.speech_queue[0].user_id: 
            return await message.answer("Сейчас не ваша очередь говорить! ")
        is_defense = False
    elif game.state == "DEFENSE":
        if not game.defense_queue or player.user_id != game.defense_queue[0].user_id: 
            return await message.answer("Сейчас не ваша очередь оправдываться!Не пытайся сломать бота, шлепок!")
        is_defense = True
    else:
        return

    if game.current_speech_task and not game.current_speech_task.done(): 
        return await message.answer("Вы уже выступаете!")

    alive_count = len(game.get_alive_players())
    speech_time = alive_count * 8
    if speech_time < 60: speech_time = 60
    elif speech_time > 90: speech_time = 90

    if is_defense:
        await message.answer(f"⏱ Игрок №{player.number}, ваши {speech_time} секунд на оправдание пошли!\nЧтобы закончить речь досрочно: /end_speech")
    else:
        await message.answer(f"⏱ Игрок №{player.number}, ваши {speech_time} секунд пошли!\nВы можете выставлять кандидатов: /nominate \nЧтобы закончить речь досрочно: /end_speech")
        
    async def timer_task():
        try:
            await asyncio.sleep(speech_time - 10)
            if player.is_alive and game.state in ["DAY", "DEFENSE"]:
                await bot.send_message(message.chat.id, f"⚠️ Игрок №{player.number}, осталось 10 секунд!")
                await asyncio.sleep(10)
                if player.is_alive and game.state in ["DAY", "DEFENSE"]:
                    await bot.send_message(message.chat.id, f"🛑 Игрок №{player.number}, время вышло!")
                    if is_defense:
                        await next_defense_speaker(game, message.chat.id)
                    else:
                        await next_speaker(game, message.chat.id)
        except asyncio.CancelledError: pass
        finally: game.current_speech_task = None

    game.current_speech_task = asyncio.create_task(timer_task())

@dp.message(Command("end_speech"))
async def cmd_end_speech(message: types.Message):
    game = games.get(message.chat.id)
    if not game: return
    
    player = game.players.get(message.from_user.id)
    if not player: return

    if game.state == "DAY" and game.speech_queue and player.user_id == game.speech_queue[0].user_id:
        if game.current_speech_task and not game.current_speech_task.done(): game.current_speech_task.cancel()
        await message.answer(f"✅ Игрок №{player.number} завершил свою речь.")
        await next_speaker(game, message.chat.id)
    elif game.state == "DEFENSE" and game.defense_queue and player.user_id == game.defense_queue[0].user_id:
        if game.current_speech_task and not game.current_speech_task.done(): game.current_speech_task.cancel()
        await message.answer(f"✅ Игрок №{player.number} завершил свою оправдательную речь.")
        await next_defense_speaker(game, message.chat.id)

@dp.message(Command("nominate"))
async def cmd_nominate(message: types.Message):
    game = games.get(message.chat.id)
    if not game or game.state != "DAY" or not game.speech_queue: return
    
    if getattr(game, 'day_count', 1) == 1:
        return await message.answer("⚠️ Сегодня первый день (день знакомств). Выставлять кандидатов на голосование запрещено!")
        
    player = game.players.get(message.from_user.id)
    if not player or player.user_id != game.speech_queue[0].user_id: 
        return await message.answer("Сейчас не ваша очередь говорить!")

    if player.has_nominated:
        return await message.answer("⚠️ Вы уже выставили одного кандидата на этом кругу!")

    alive_players = game.get_alive_players()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"№{t.number} ({t.name})", callback_data=f"nom|{message.chat.id}|{t.number}")]
        for t in alive_players
    ] + [[InlineKeyboardButton(text="❌ Отмена (передумал)", callback_data=f"nom|{message.chat.id}|0")]])
    
    await message.answer("Кого вы хотите выставить на голосование?", reply_markup=kb)

@dp.callback_query(F.data.startswith("nom|"))
async def handle_nomination_callback(callback: types.CallbackQuery):
    data = callback.data.split("|")
    chat_id = int(data[1])
    target_num = int(data[2])
    
    game = games.get(chat_id)
    if not game or game.state != "DAY" or not game.speech_queue: 
        return await callback.answer("Действие недоступно.", show_alert=True)
        
    player = game.players.get(callback.from_user.id)
    
    if not player or player.user_id != game.speech_queue[0].user_id: 
        return await callback.answer("Не лезь, сейчас не твоя очередь!", show_alert=True)
        
    if player.has_nominated:
        return await callback.answer("Вы уже выставили кандидата!", show_alert=True)

    if target_num == 0:
        return await callback.message.edit_text("❌ Вы отменили выставление. Вы можете продолжить свою речь.")

    if target_num not in game.players_by_number or not game.players_by_number[target_num].is_alive:
        return await callback.answer("Этот игрок уже покинул стол!", show_alert=True)

    if target_num not in game.nominated:
        game.nominated.append(target_num)
        player.has_nominated = True 
        await callback.message.edit_text(f"👉 Игрок №{player.number} выставил Игрока №{target_num} на голосование.")
    else:
        await callback.answer("Этот игрок уже выставлен на голосование!", show_alert=True)

@dp.message(Command("nominated"))
async def cmd_nominated(message: types.Message):
    game = games.get(message.chat.id)
    if game and game.nominated: await message.answer("Выставлены: " + ", ".join(map(str, game.nominated)))
    else: await message.answer("Пока никто не выставлен.")

# --- ФАЗА ОПРАВДАНИЙ, АВТОКИКА И ГОЛОСОВАНИЯ ---

async def next_defense_speaker(game: Game, chat_id: int):
    if game.defense_queue: game.defense_queue.popleft() 
    
    while game.defense_queue and game.defense_queue[0].is_glued:
        glued_p = game.defense_queue.popleft()
        await bot.send_message(chat_id, f"🤐 Игрок №{glued_p.number} заклеен Вором и пропускает свою оправдательную речь.")

    if game.defense_queue:
        next_p = game.defense_queue[0]
        await bot.send_message(chat_id, f"🗣 Очередь оправдываться Игрока №{next_p.number}. Напишите /speech для начала речи.")
    else:
        await bot.send_message(chat_id, "🎙 Все оправдательные речи окончены!")
        await proceed_to_voting_or_autokick(game, chat_id)

async def proceed_to_voting_or_autokick(game: Game, chat_id: int):
    if len(game.nominated) == 1:
        killed_num = game.nominated[0]
        await bot.send_message(chat_id, f"⚡️ Так как выставлен всего 1 игрок, голосование не проводится. Срабатывает АВТОКИК!")
        
        if game.players_by_number[killed_num].has_alibi:
            await bot.send_message(chat_id, f"🛡 Игрок №{killed_num} должен был покинуть стол, но у него оказалось АЛИБИ! Он выживает.")
        else:
            game.players_by_number[killed_num].is_alive = False
            await bot.send_message(chat_id, f"💀 Игрок №{killed_num} покидает стол!")
            
        if await check_victory(game, chat_id): return
        
        await bot.send_message(chat_id, "Город засыпает...")
        await start_night_phase(game, chat_id)
    else:
        game.state = "VOTING"
        game.current_votes = {num: 0 for num in game.nominated}
        game.vote_history = {} 
        game.voting_queue = game.build_daily_queue() 
        await bot.send_message(chat_id, f"🗳 Начинаем голосование! Выставлены: {game.nominated}.\nПервым голосует Игрок №{game.voting_queue[0].number}. Пишите /vote")

@dp.message(Command("voted"))
async def cmd_voted(message: types.Message):
    game = games.get(message.chat.id)
    if not game or game.state not in ["VOTING", "REVOTE", "BALANCE"]:
        return await message.answer("Сейчас не идет голосование!")
        
    if not getattr(game, 'vote_history', None):
        return await message.answer("Пока никто не проголосовал.")
        
    text = "📊 <b>Текущие результаты:</b>\n\n"
    
    if game.state in ["VOTING", "REVOTE"]:
        for t_num, votes in game.current_votes.items():
            text += f"Против №{t_num}: {votes} голосов\n"
    else:
        text += f"Оправдать: {game.current_votes.get('acquit', 0)}\n"
        text += f"Убить всех: {game.current_votes.get('kill', 0)}\n"
        text += f"Переголосовать: {game.current_votes.get('revote', 0)}\n"
        
    text += "\n📝 <b>Кто как проголосовал:</b>\n"
    for p_num, v_target in game.vote_history.items():
        if game.state in ["VOTING", "REVOTE"]:
            text += f"Игрок №{p_num} ➡️ против №{v_target}\n"
        else:
            text += f"Игрок №{p_num} ➡️ {v_target}\n"
            
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("vote"))
async def cmd_vote(message: types.Message):
    game = games.get(message.chat.id)
    if not game or game.state not in ["VOTING", "REVOTE"]: return
    player = game.players.get(message.from_user.id)
    if not player or not game.voting_queue or player.user_id != game.voting_queue[0].user_id: 
        return await message.answer("Сейчас не ваша очередь голосовать!")

    allowed = game.balance_players if game.state == "REVOTE" else game.nominated
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"№{num} ({game.players_by_number[num].name})", callback_data=f"v|{message.chat.id}|{num}")]
        for num in allowed
    ])
    await message.answer("Против кого вы голосуете?", reply_markup=kb)

@dp.callback_query(F.data.startswith("v|"))
async def handle_vote_callback(callback: types.CallbackQuery):
    data = callback.data.split("|")
    chat_id = int(data[1])
    target_num = int(data[2])
    
    game = games.get(chat_id)
    if not game or game.state not in ["VOTING", "REVOTE"]: 
        return await callback.answer("Голосование сейчас не идет.", show_alert=True)
        
    player = game.players.get(callback.from_user.id)
    if not player or not game.voting_queue or player.user_id != game.voting_queue[0].user_id: 
        return await callback.answer("Сейчас не ваша очередь!", show_alert=True)
        
    allowed = game.balance_players if game.state == "REVOTE" else game.nominated
    if target_num not in allowed: 
        return await callback.answer("За этого игрока нельзя голосовать!", show_alert=True)

    game.current_votes[target_num] += 1
    game.vote_history[player.number] = target_num
    game.voting_queue.popleft()
    
    await callback.message.edit_text(f"🗣 Игрок №{player.number} проголосовал против Игрока №{target_num}!")

    if not game.voting_queue: await calculate_votes(game, chat_id)
    else: await bot.send_message(chat_id, f"Следующий голосует Игрок №{game.voting_queue[0].number}. Напишите /vote")

async def calculate_votes(game: Game, chat_id: int):
    max_votes = max(game.current_votes.values())
    leaders = [num for num, votes in game.current_votes.items() if votes == max_votes]

    if len(leaders) == 1:
        killed_num = leaders[0]
        if game.players_by_number[killed_num].has_alibi:
            await bot.send_message(chat_id, f"🛡 Игрок №{killed_num} должен был покинуть стол, но у него оказалось АЛИБИ! Он выживает.")
        else:
            game.players_by_number[killed_num].is_alive = False
            await bot.send_message(chat_id, f"💀 Игрок №{killed_num} покидает стол!")
            
        if await check_victory(game, chat_id): return
        
        await bot.send_message(chat_id, "Город засыпает...")
        await start_night_phase(game, chat_id)
    else:
        if game.revote_count >= 1:
            await bot.send_message(chat_id, "⚖️ Голоса снова разделились! Автоматическое оправдание. Город засыпает...")
            await start_night_phase(game, chat_id)
            return
            
        game.balance_players = leaders
        game.state = "BALANCE"
        game.current_votes = {"acquit": 0, "kill": 0, "revote": 0}
        game.vote_history = {}
        game.voting_queue = game.build_daily_queue()
        await bot.send_message(chat_id, f"⚖️ Баланс между: {leaders}.\nПервым голосует Игрок №{game.voting_queue[0].number}. Пишите /balance")

@dp.message(Command("balance"))
async def cmd_balance_vote(message: types.Message):
    game = games.get(message.chat.id)
    if not game or game.state != "BALANCE": return
    player = game.players.get(message.from_user.id)
    if not player or not game.voting_queue or player.user_id != game.voting_queue[0].user_id: 
        return await message.answer("Сейчас не ваша очередь!")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕊 Оправдать", callback_data=f"bal|{message.chat.id}|1")],
        [InlineKeyboardButton(text="💀 Убить всех", callback_data=f"bal|{message.chat.id}|2")],
        [InlineKeyboardButton(text="🔄 Переголосовать", callback_data=f"bal|{message.chat.id}|3")]
    ])
    await message.answer("Ваш выбор на балансе?", reply_markup=kb)

@dp.callback_query(F.data.startswith("bal|"))
async def handle_balance_callback(callback: types.CallbackQuery):
    data = callback.data.split("|")
    chat_id = int(data[1])
    choice = int(data[2])
    
    game = games.get(chat_id)
    if not game or game.state != "BALANCE": return await callback.answer("Баланс не идет.", show_alert=True)
    player = game.players.get(callback.from_user.id)
    if not player or not game.voting_queue or player.user_id != game.voting_queue[0].user_id: 
        return await callback.answer("Сейчас не ваша очередь!", show_alert=True)
        
    options = {1: "acquit", 2: "kill", 3: "revote"}
    names = {1: "Оправдать", 2: "Убить всех", 3: "Переголосовать"}
    
    game.current_votes[options[choice]] += 1
    game.vote_history[player.number] = names[choice]
    game.voting_queue.popleft()
    
    await callback.message.edit_text(f"🗣 Игрок №{player.number} выбрал: {names[choice]}!")

    if not game.voting_queue: await resolve_balance(game, chat_id)
    else: await bot.send_message(chat_id, f"Следующий голосует Игрок №{game.voting_queue[0].number}. Напишите /balance")

async def resolve_balance(game: Game, chat_id: int):
    v = game.current_votes
    max_v = max(v.values())
    
    if v["revote"] == max_v:
        game.revote_count += 1
        game.state = "REVOTE"
        game.current_votes = {num: 0 for num in game.balance_players}
        game.vote_history = {}
        game.voting_queue = game.build_daily_queue()
        await bot.send_message(chat_id, "🔄 ПЕРЕГОЛОСОВАНИЕ! Пишите /vote за игроков на балансе.")
    elif v["acquit"] == max_v:
        await bot.send_message(chat_id, "🕊 Все ОПРАВДАНЫ.\nГород засыпает...")
        await start_night_phase(game, chat_id)
    else:
        killed = []
        saved = []
        for num in game.balance_players: 
            if game.players_by_number[num].has_alibi: saved.append(num)
            else:
                game.players_by_number[num].is_alive = False
                killed.append(num)
        
        killed_str = ", ".join(map(str, killed)) if killed else "никто"
        msg = f"💀 По результатам баланса убиты: {killed_str}."
        if saved: 
            saved_str = ", ".join(map(str, saved))
            msg += f"\n🛡 Спасены алиби: {saved_str}."
            
        await bot.send_message(chat_id, msg)
        
        if await check_victory(game, chat_id): return
        
        await bot.send_message(chat_id, "Город засыпает...")
        await start_night_phase(game, chat_id)

# --- ФАЗА НОЧИ ДЛЯ ВСЕХ РОЛЕЙ И ТАЙМЕРЫ ---

async def thief_timeout_logic(game: Game, chat_id: int, current_day: int):
    await asyncio.sleep(60) 
    if game.state == "NIGHT_THIEF" and game.day_count == current_day:
        await bot.send_message(chat_id, "🤐 Вор никого не заклеил.")
        game.expected_night_actors.clear() 
        thief = next((p for p in game.get_alive_players() if p.role == "Вор"), None)
        if thief: thief.last_rek = None
        await start_night_others(game, chat_id) 

async def night_timeout_logic(game: Game, chat_id: int, current_day: int):
    await asyncio.sleep(120) 
    if game.state == "NIGHT" and game.day_count == current_day:
        for uid in game.expected_night_actors.keys():
            try:
                await bot.send_message(uid, "⏳ <b>Осталась 1 минута!</b> Поторопитесь сделать свой выбор, иначе ваш ход сгорит.", parse_mode="HTML")
            except: pass
        
        await asyncio.sleep(60) 
        
        if game.state == "NIGHT" and game.day_count == current_day:
            await bot.send_message(chat_id, "⏰ <b>Время вышло!</b> Ночь затянулась.", parse_mode="HTML")
            game.expected_night_actors.clear() 
            await resolve_night(game, chat_id) 

@dp.message(Command("start_night"))
async def cmd_start_night(message: types.Message):
    game = games.get(message.chat.id)
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔️ Эта команда доступна только создателю игры!")
    if not game or game.state in ["LOBBY", "NIGHT", "FINISHED"]: return
    if game.current_speech_task and not game.current_speech_task.done(): game.current_speech_task.cancel()
    await message.answer("🌙 Принудительно наступает Ночь! Город засыпает...")
    await start_night_phase(game, message.chat.id)

async def start_night_phase(game: Game, chat_id: int):
    game.state = "NIGHT_THIEF"
    game.night_actions = {} 
    game.expected_night_actors = {} 
    
    asyncio.create_task(thief_timeout_logic(game, chat_id, game.day_count))
    
    for p in game.players.values():
        p.is_glued = False
        p.has_alibi = False

    alive_players = game.get_alive_players()
    game.mafia_team = ["Мафия", "Дон", "Адвокат", "Ниндзя"]
    
    thief = next((p for p in alive_players if p.role == "Вор"), None)
    thief_in_preset = "Вор" in game.current_preset

    if thief:
        await bot.send_message(chat_id, "🌙 Ждем ход Вора (у него есть 1 минута)...")
        game.expected_night_actors[thief.user_id] = ["rek"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"№{t.number} ({t.name})", callback_data=f"n|{chat_id}|rek|{t.number}")] 
            for t in alive_players
        ] + [[InlineKeyboardButton(text="Никого не клеить", callback_data=f"n|{chat_id}|rek|0")]])
        
        try: 
            await bot.send_message(thief.user_id, "Кого будем клеить?", reply_markup=kb)
        except Exception as e: 
            print(f"Ошибка отправки Вору: {e}")
            await bot.send_message(chat_id, "🤐 Вор никого не заклеил.")
            game.expected_night_actors.clear()
            if thief: thief.last_rek = None
            await start_night_others(game, chat_id)

    elif thief_in_preset:
        await bot.send_message(chat_id, "🌙 Ждем ход Вора...")
        await asyncio.sleep(random.randint(20, 45))
        await bot.send_message(chat_id, "🤐 Вор никого не заклеил.")
        await start_night_others(game, chat_id)
    else:
        await start_night_others(game, chat_id)

async def start_night_others(game: Game, chat_id: int):
    game.state = "NIGHT"
    game.expected_night_actors.clear()
    alive_players = game.get_alive_players()
    
    await bot.send_message(chat_id, "⏳ Мафия и активные роли делают свой ход. У вас есть ровно 3 минуты на все действия!")
    
    asyncio.create_task(night_timeout_logic(game, chat_id, game.day_count))
    
    for p in alive_players:
        if p.role == "Вор" or p.is_glued: continue 
        
        actions = []
        if p.role in game.mafia_team: actions.append(("vote", "Кого убиваем?"))
        if p.role == "Доктор": actions.append(("heal", "Кого будем лечить? (нельзя того же, что и вчера)"))
        if p.role == "Тула": actions.append(("tula", "К кому идем? (хил + алиби)"))
        if p.role == "Шериф": actions.append(("check_s", "Кого проверим на мафию?"))
        if p.role == "Дон": actions.append(("check_d", "Кого проверим на Шерифа?"))
        if p.role == "Адвокат": actions.append(("alibi", "Кому даем алиби на день?"))
        if p.role == "Ниндзя": actions.append(("sur", "В кого кидаем сюрикен?"))
        if p.role == "Маньяк без бинтов": actions.append(("man_k", "Кого убиваем?"))
        if p.role == "Маньяк с бинтами": 
            actions.append(("man_k", "Кого убиваем? (ИЛИ выберите лечение себя)"))
            actions.append(("man_h", "Вылечить себя?"))
        if p.role == "Двуликий":
            if getattr(p, 'found_mafia', False): actions.append(("dvul_k", "Кого убиваем?"))
            else: actions.append(("dvul_j", "Ищем мафию (проверка):"))

        if actions:
            game.expected_night_actors[p.user_id] = [act[0] for act in actions]
            game.night_actions.setdefault(p.user_id, {})
            for act_code, text in actions:
                if act_code == "man_h":
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Лечить себя", callback_data=f"n|{chat_id}|{act_code}|{p.number}")]])
                else:
                    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"№{t.number} ({t.name})", callback_data=f"n|{chat_id}|{act_code}|{t.number}")] for t in alive_players])
                try: await bot.send_message(p.user_id, text, reply_markup=kb)
                except Exception as e: print(f"Ошибка отправки игроку {p.name}: {e}")

    if not game.expected_night_actors:
        await resolve_night(game, chat_id)

@dp.callback_query(F.data.startswith("n|"))
async def handle_night_action(callback: types.CallbackQuery):
    data = callback.data.split("|")
    chat_id, act_code, target_num = int(data[1]), data[2], int(data[3])
    
    game = games.get(chat_id)
    if not game or game.state not in ["NIGHT", "NIGHT_THIEF"]: return await callback.answer("Ночь уже прошла!", show_alert=True)
    
    user_id = callback.from_user.id
    player = game.players.get(user_id)
    
    if not player or user_id not in game.expected_night_actors or act_code not in game.expected_night_actors[user_id]:
        return await callback.answer("Это действие вам сейчас недоступно.", show_alert=True)

    if game.state == "NIGHT_THIEF" and act_code == "rek":
        if target_num != 0 and getattr(player, 'last_rek', None) == target_num:
            return await callback.answer("Нельзя клеить одного и того же игрока две ночи подряд!", show_alert=True)

        game.expected_night_actors[user_id].remove("rek")
        if target_num == 0:
            await callback.message.edit_text("✅ Вы решили никого не клеить.")
            await bot.send_message(chat_id, "🤐 Вор никого не заклеил.")
            player.last_rek = 0
        else:
            target = game.players_by_number[target_num]
            target.is_glued = True
            player.last_rek = target_num
            await callback.message.edit_text(f"✅ Вы заклеили Игрока №{target_num}.")
            await bot.send_message(chat_id, f"🤐 Вор заклеил Игрока №{target_num}! Он пропускает день.")
        
        await start_night_others(game, chat_id)
        return
        
    if act_code in ["heal", "tula"] and player.last_healed == target_num: return await callback.answer("Нельзя лечить этого игрока две ночи подряд!", show_alert=True)
    if act_code == "alibi" and player.last_alibi == target_num: return await callback.answer("Нельзя давать алиби этому игроку две ночи подряд!", show_alert=True)
    if act_code == "man_h" and getattr(player, 'last_man_heal', False): return await callback.answer("Нельзя лечить себя 2 дня подряд!", show_alert=True)
        
    game.night_actions[user_id][act_code] = target_num

    if act_code == "check_d":
        t_player = game.players_by_number[target_num]
        ans = f"✅ Игрок №{target_num} — ШЕРИФ!" if t_player.role == "Шериф" else f"❌ Игрок №{target_num} — НЕ ШЕРИФ."
        await bot.send_message(user_id, ans)
    elif act_code == "check_s":
        t_player = game.players_by_number[target_num]
        
        is_bad_dvul = (t_player.role == "Двуликий" and getattr(t_player, 'found_mafia', False) and getattr(t_player, 'found_mafia_day', -1) < game.day_count)
        
        if t_player.role in game.mafia_team or is_bad_dvul: 
            ans = f"✅ Игрок №{target_num} — МАФИЯ ({t_player.role})!"
        else: 
            ans = f"❌ Игрок №{target_num} — НЕ МАФИЯ."
        await bot.send_message(user_id, ans)
    elif act_code == "dvul_j":
        t_player = game.players_by_number[target_num]
        if t_player.role in game.mafia_team:
            player.found_mafia = True
            player.found_mafia_day = game.day_count
            maf_list = ", ".join([f"№{p.number} ({p.role})" for p in game.get_alive_players() if p.role in game.mafia_team])
            await bot.send_message(user_id, f"🎯 Вы нашли Мафию! Состав: {maf_list}. Со следующей ночи вы убиваете сами.")
            for maf in game.get_alive_players():
                if maf.role in game.mafia_team: await bot.send_message(maf.user_id, f"🎭 Двуликий нашел нас! Это Игрок №{player.number}.")
        else:
            await bot.send_message(user_id, f"❌ Игрок №{target_num} не состоит в Мафии.")
    
    if act_code == "man_k" and "man_h" in game.expected_night_actors[user_id]:
        game.expected_night_actors[user_id].remove("man_h")
        player.last_man_heal = False
    elif act_code == "man_h":
        game.expected_night_actors[user_id].remove("man_k")
        player.last_man_heal = True

    game.expected_night_actors[user_id].remove(act_code)
    await callback.message.edit_text(f"✅ Выбор принят: Игрок №{target_num}")
    
    all_done = all(len(acts) == 0 for acts in game.expected_night_actors.values())
    if all_done: await resolve_night(game, chat_id)

@dp.message(Command("skip_night"))
async def cmd_skip_night(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔️ Эта команда доступна только создателю игры!")
    game = games.get(message.chat.id)
    if game:
        if game.state == "NIGHT_THIEF":
            await bot.send_message(message.chat.id, "🤐 Вор никого не заклеил.")
            thief = next((p for p in game.get_alive_players() if p.role == "Вор"), None)
            if thief: thief.last_rek = None
            await start_night_others(game, message.chat.id)
        elif game.state == "NIGHT":
            await resolve_night(game, message.chat.id)

async def resolve_night(game: Game, chat_id: int):
    alive_players = game.get_alive_players()
    
    # --- ОЧИСТКА ПАМЯТИ И РАНДОМНЫЕ ХОДЫ ДЛЯ СПЯЩИХ ---
    for p in alive_players:
        if p.user_id not in game.night_actions:
            if p.is_glued: continue # Заклеенные просто спят законно
            
            if p.role == "Ниндзя":
                target = random.choice(alive_players)
                game.night_actions.setdefault(p.user_id, {})["sur"] = target.number
                asyncio.create_task(bot.send_message(p.user_id, f"⚠️ Вы проспали ход! Бот случайно бросил ваш сюрикен в Игрока №{target.number}."))
            
            elif p.role == "Тула":
                valid_targets = [t for t in alive_players if t.number != p.last_healed]
                if valid_targets:
                    target = random.choice(valid_targets)
                    game.night_actions.setdefault(p.user_id, {})["tula"] = target.number
                    asyncio.create_task(bot.send_message(p.user_id, f"⚠️ Вы проспали ход! Бот случайно отправил вас к Игроку №{target.number}."))
                else:
                    p.last_healed = None
            
            elif p.role in ["Маньяк без бинтов", "Маньяк с бинтами"]:
                target = random.choice(alive_players)
                game.night_actions.setdefault(p.user_id, {})["man_k"] = target.number
                asyncio.create_task(bot.send_message(p.user_id, f"⚠️ Вы проспали ход! Бот случайно отправил вас убивать Игрока №{target.number}."))
                if p.role == "Маньяк с бинтами": p.last_man_heal = False

            elif p.role == "Двуликий" and getattr(p, 'found_mafia', False):
                target = random.choice(alive_players)
                game.night_actions.setdefault(p.user_id, {})["dvul_k"] = target.number
                asyncio.create_task(bot.send_message(p.user_id, f"⚠️ Вы проспали ход! Бот случайно отправил вас убивать Игрока №{target.number}."))

            else:
                # Доктор, Адвокат, Шериф и т.д. просто пропускают ход
                if p.role == "Доктор": p.last_healed = None
                if p.role == "Адвокат": p.last_alibi = None
            
    healed = set()
    mafia_votes = {}
    killed_this_night = set()
    putana_client = None
    
    shurikens_before = {p.number for p in game.get_alive_players() if p.surikens > 0}
    mafia_blocked = any(p.is_glued for p in game.get_alive_players() if p.role in game.mafia_team)
    
    actions = []
    for uid, acts in game.night_actions.items():
        for code, target in acts.items():
            actions.append({"actor": game.players[uid], "code": code, "target": game.players_by_number[target]})

    for a in actions:
        if a["actor"].is_glued: continue
        if a["code"] == "heal":
            healed.add(a["target"].number)
            a["actor"].last_healed = a["target"].number
            a["target"].surikens = 0 
        elif a["code"] == "tula":
            healed.add(a["target"].number)
            a["target"].has_alibi = True
            a["actor"].last_healed = a["target"].number
            a["target"].surikens = 0
            putana_client = a["target"]
        elif a["code"] == "man_h":
            healed.add(a["target"].number) 

    for a in actions:
        if a["code"] == "alibi" and not a["actor"].is_glued:
            a["target"].has_alibi = True
            a["actor"].last_alibi = a["target"].number

    shurikened_this_night = [] 
    
    for a in actions:
        if a["code"] == "sur" and not a["actor"].is_glued:
            if a["target"].number not in healed: 
                a["target"].surikens += 1
                shurikened_this_night.append(a["target"].number)
        
    mafia_victim = None
    if not mafia_blocked:
        for a in actions:
            if a["code"] == "vote" and not a["actor"].is_glued:
                weight = 2 if a["actor"].role == "Дон" else 1
                mafia_votes[a["target"].number] = mafia_votes.get(a["target"].number, 0) + weight
        if mafia_votes:
            max_v = max(mafia_votes.values())
            leaders = [t for t, v in mafia_votes.items() if v == max_v]
            if leaders: mafia_victim = game.players_by_number[random.choice(leaders)]
        else:
            # --- ВСЯ МАФИЯ ПРОСПАЛА - СЛУЧАЙНЫЙ ВЫСТРЕЛ ---
            alive_players = game.get_alive_players()
            if alive_players:
                mafia_victim = random.choice(alive_players)

    solo_victims = []
    for a in actions:
        if a["actor"].is_glued: continue
        if a["code"] in ["man_k", "dvul_k"]: solo_victims.append(a["target"])

    if mafia_victim:
        if mafia_victim.number not in healed and mafia_victim.role != "Бессмертный":
            killed_this_night.add(mafia_victim.number)

    for victim in solo_victims:
        if victim.number not in healed and victim.role != "Бессмертный": 
            killed_this_night.add(victim.number)

    for p in game.get_alive_players():
        if p.surikens >= 2 and p.number not in healed: 
            if p.role == "Бессмертный":
                p.surikens = 0 
            else:
                killed_this_night.add(p.number)

    for p in game.get_alive_players():
        if p.role == "Тула" and p.number in killed_this_night:
            if putana_client and putana_client.number != p.number:
                if putana_client.role != "Бессмертный":
                    killed_this_night.add(putana_client.number)
    
    announcement = "☀️ Город просыпается.\n\n"
    if killed_this_night:
        for num in killed_this_night: game.players_by_number[num].is_alive = False
        announcement += f"💀 Этой ночью были убиты: {', '.join(map(str, killed_this_night))}.\n"
    else:
        announcement += "🕊 Этой ночью никто не умер!\n"
        
    lost_shurikens = [num for num in shurikens_before if game.players_by_number[num].is_alive and game.players_by_number[num].surikens == 0]
    if lost_shurikens:
        announcement += f"🩹 Сюрикены были успешно извлечены (сброшены) у игроков: {', '.join(map(str, lost_shurikens))}\n"

    current_shurikens = [p.number for p in game.get_alive_players() if p.surikens == 1]
    if current_shurikens:
        announcement += f"🥷 Внимание! По 1 сюрикену сейчас висит на игроках: {', '.join(map(str, current_shurikens))}\n"
        
    await bot.send_message(chat_id, announcement)

    if await check_victory(game, chat_id): return

    game.day_count += 1
    game.state = "DAY"
    await start_day_phase(game, chat_id)

async def set_default_commands(bot: Bot):
    commands = [
        BotCommand(command="alive", description="Показать живых игроков"),
        BotCommand(command="speech", description="Начать свою речь"),
        BotCommand(command="end_speech", description="Завершить речь досрочно"),
        BotCommand(command="nominate", description="Выставить на голосование"),
        BotCommand(command="nominated", description="Кого уже выставили"),
        BotCommand(command="vote", description="Проголосовать на суде"),
        BotCommand(command="voted", description="Кто за кого проголосовал"),
        BotCommand(command="balance", description="Голосовать при автокатастрофе"),
        BotCommand(command="roles", description="Список ролей в игре"),
        BotCommand(command="description", description="Полное описание ролей"),
        BotCommand(command="help", description="Справка по боту")
    ]
    # Отправляем этот список в Telegram
    await bot.set_my_commands(commands)
async def main():
    await set_default_commands(bot) # <-- Устанавливаем меню команд
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())