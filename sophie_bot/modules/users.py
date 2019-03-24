from sophie_bot import MONGO, REDIS, bot
from sophie_bot.events import flood_limit, register

from telethon.tl.types import ChannelParticipantsAdmins
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import MessageEntityMentionName

import ujson


@register()
async def event(event):
    await update_users(event)


async def update_users(event):
    chat_id = event.chat_id
    user_id = event.from_id
    try:
        chat_name = event.chat.title
    except Exception as err:
        await event.edit(str(err))
        chat_name = "Local"
    user = await bot.get_entity(user_id)
    chat = await bot.get_entity(chat_id)

    old_chats = MONGO.chat_list.find({'chat_id': chat_id})
    old_users = MONGO.user_list.find({'user_id': user_id})

    new_chat = [chat_id]

    if old_users:
        for old_user in old_users:
            if 'chats' in old_user:
                new_chat = old_user['chats']
                if chat_id not in new_chat:
                    new_chat.append(chat_id)

            MONGO.user_list.delete_one({'_id': old_user['_id']})
    if old_chats:
        for old_chat in old_chats:
            MONGO.chat_list.delete_one({'_id': old_chat['_id']})

    if not chat.username:
        chatnick = None
    else:
        chatnick = chat.username

    MONGO.chat_list.insert_one(
        {"chat_id": chat_id,
         "chat_title": chat_name,
         "chat_nick": chatnick})
    MONGO.user_list.insert_one(
        {'user_id': user_id,
         'first_name': user.first_name,
         'last_name': user.last_name,
         'username': user.username,
         'user_lang': user.lang_code,
         'chats': new_chat})

    try:
        if event.message.reply_to_msg_id:
            msg = await event.get_reply_message()
            user_id = msg.from_id
            user = await bot.get_entity(user_id)
            old_users = MONGO.user_list.find({'user_id': user_id})
            if old_users:
                for old_user in old_users:
                    MONGO.user_list.delete_one({'_id': old_user['_id']})

            MONGO.user_list.insert_one(
                {'user_id': user_id,
                 'first_name': user.first_name,
                 'last_name': user.last_name,
                 'username': user.username,
                 'user_lang': user.lang_code})
    except Exception as err:
        await event.edit(str(err))


@register(incoming=True, pattern="^/test ?(.*)")
async def event(event):
    msg = await event.get_reply_message()
    print(msg)
    await event.reply(msg)


async def update_admin_cache(chat_id):
    admin_list = await bot.get_participants(
        int(chat_id), filter=ChannelParticipantsAdmins())
    admins = []
    for admin in admin_list:
        admins.append(admin.id)
    dump = ujson.dumps(admins)
    REDIS.set('admins_cache_{}'.format(chat_id), dump)
    REDIS.expire('admins_cache_{}'.format(chat_id), 3600)


async def is_user_admin(chat_id, user_id):
    dump = REDIS.get('admins_cache_{}'.format(chat_id))
    if not dump:
        await update_admin_cache(chat_id)
        dump = REDIS.get('admins_cache_{}'.format(chat_id))

    admins = ujson.decode(dump)
    if user_id in admins:
        return True
    else:
        return False


@register(incoming=True, pattern="^/adminlist")
async def event(event):
    res = flood_limit(event.chat_id, 'admins')
    if res == 'EXIT':
        return
    elif res is True:
        await event.reply('**Flood detected! **\
Please wait 3 minutes before using this command')
        return
    msg = await event.reply("Updating cache now...")
    await update_admin_cache(event.chat_id)
    dump = REDIS.get('admins_cache_{}'.format(event.chat_id))
    admins = ujson.decode(dump)
    text = '**Admin in this group:**\n'
    for admin in admins:
        print(admin)
        H = MONGO.user_list.find_one({'user_id': admin})
        print(H)
        if H:
            text += '- {} ({})\n'.format(H['first_name'], H['user_id'])

    await msg.edit(text)


async def get_user_and_text(event):
    msg = event.message.raw_text.split()
    if event.reply_to_msg_id:
        if len(msg) >= 2:
            text = event.message.raw_text.split(" ", 1)[1]
        else:
            text = None
        msg = await event.get_reply_message()
        user = MONGO.user_list.find_one(
            {'user_id': msg.from_id}
        )
    else:
        input_str = event.pattern_match.group(1)
        if event.message.entities is not None:
            mention_entity = event.message.entities
            probable_user_mention_entity = mention_entity[0]
            if len(msg) >= 3:
                text = event.message.raw_text.split(" ", 2)[2]
            else:
                text = None

            if type(probable_user_mention_entity) == \
                    MessageEntityMentionName:
                user = probable_user_mention_entity
            else:
                if input_str.isdigit():
                    input_str = int(input_str)
                # the disgusting CRAP way, of doing the thing
                if len(msg) >= 3:
                    text = event.message.raw_text.split(" ", 2)[2]
                else:
                    text = None

                if '@' in event.message.raw_text.split(" ", 2)[1]:
                    input_str = event.message.raw_text.split(" ", 2)[1][1:]
                    print(input_str)
                    user = MONGO.user_list.find_one(
                        {'username': input_str}
                    )
                else:
                    user = int(event.message.raw_text.split(" ", 2)[1])
                    user = MONGO.user_list.find_one(
                        {'user_id': input_str}
                    )
        else:
            if len(msg) >= 3:
                text = event.message.raw_text.split(" ", 2)[2]
            else:
                text = None
            try:
                user = await event.client.get_entity(input_str)
            except Exception as err:
                await event.edit(str(err))
                return None

    return user, text


async def get_id_by_nick(data):
    # Check if data is user_id
    user = MONGO.user_list.find_one({'username': data.replace('@', "")})
    if user:
        return user['user_id']

    user = await bot(GetFullUserRequest(data))
    return user
