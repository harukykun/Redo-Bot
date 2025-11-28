import os
import discord
from discord.ext import commands
from pymongo import MongoClient
from datetime import datetime, timezone
from dotenv import load_dotenv

# 1. Tải biến môi trường
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
MONGO_URI = os.getenv('MONGODB_URI')

# 2. Kết nối MongoDB
# Lưu ý: Trên Railway, Mongo URI thường có dạng mongodb://...
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['discord_bot_db'] # Tên database
logs_collection = db['message_logs'] # Tên collection (bảng)

# 3. Cấu hình Bot Discord
intents = discord.Intents.default()
intents.message_content = True  # Quan trọng: Để đọc được nội dung tin nhắn
intents.members = True          # Để lấy thông tin thành viên (tag)

bot = commands.Bot(command_prefix='!', intents=intents)

# --- Sự kiện: Bot đã sẵn sàng ---
@bot.event
async def on_ready():
    print(f'✅ Bot đã đăng nhập với tên: {bot.user.name}')
    print('🚀 Đang theo dõi tin nhắn...')

# --- Sự kiện: Tin nhắn bị XÓA ---
@bot.event
async def on_message_delete(message):
    # Bỏ qua tin nhắn của bot hoặc tin nhắn rỗng (chỉ có ảnh/embed)
    if message.author.bot or not message.content:
        return

    log_entry = {
        'message_id': message.id,
        'author_id': message.author.id,
        'author_name': message.author.name,
        'content_before': message.content,
        'content_after': None, # Xóa thì không có content sau
        'type': 'DELETE',
        'channel_id': message.channel.id,
        'created_at': datetime.now(timezone.utc)
    }
    
    try:
        logs_collection.insert_one(log_entry)
        # print(f"Đã lưu tin nhắn bị xóa của {message.author.name}")
    except Exception as e:
        print(f"Lỗi lưu DB (Delete): {e}")

# --- Sự kiện: Tin nhắn bị CHỈNH SỬA ---
@bot.event
async def on_message_edit(before, after):
    # Bỏ qua nếu nội dung không đổi (ví dụ Discord chỉ load link preview), bot, hoặc rỗng
    if before.content == after.content or before.author.bot or not before.content:
        return

    log_entry = {
        'message_id': before.id,
        'author_id': before.author.id,
        'author_name': before.author.name,
        'content_before': before.content,
        'content_after': after.content,
        'type': 'EDIT',
        'channel_id': before.channel.id,
        'created_at': datetime.now(timezone.utc)
    }

    try:
        logs_collection.insert_one(log_entry)
        # print(f"Đã lưu tin nhắn chỉnh sửa của {before.author.name}")
    except Exception as e:
        print(f"Lỗi lưu DB (Edit): {e}")

# --- Lệnh: !chaydidau ---
@bot.command(name='chaydidau')
async def chaydidau(ctx, member: discord.Member = None, index: int = 1):
    # Kiểm tra cú pháp
    if member is None:
        await ctx.reply("Sai cú pháp! Vui lòng dùng: `!chaydidau <@tag> <số thứ tự>`")
        return
    
    if index < 1:
        index = 1

    try:
        # Truy vấn MongoDB: Tìm theo ID người dùng, Sắp xếp mới nhất -> cũ nhất
        # Skip: Bỏ qua (index - 1) tin nhắn đầu để lấy tin thứ index
        cursor = logs_collection.find({'author_id': member.id})\
                                .sort('created_at', -1)\
                                .skip(index - 1)\
                                .limit(1)
        
        # Chuyển con trỏ thành list để lấy dữ liệu
        result = list(cursor)

        if not result:
            await ctx.reply(f"🕵️ Không tìm thấy tin nhắn đã xóa/sửa thứ #{index} nào của **{member.display_name}**.")
            return

        data = result[0]
        
        # Tạo Embed hiển thị đẹp mắt
        embed_color = discord.Color.red() if data['type'] == 'DELETE' else discord.Color.orange()
        title_type = "ĐÃ XÓA 🗑️" if data['type'] == 'DELETE' else "ĐÃ CHỈNH SỬA ✏️"
        
        embed = discord.Embed(
            title=f"Tin nhắn {title_type} của {data['author_name']}",
            color=embed_color,
            timestamp=data['created_at']
        )
        
        # Hiển thị nội dung
        if data['type'] == 'EDIT':
            embed.add_field(name="Trước khi sửa:", value=data['content_before'], inline=False)
            embed.add_field(name="Sau khi sửa:", value=data['content_after'], inline=False)
        else:
            embed.add_field(name="Nội dung:", value=data['content_before'], inline=False)
            
        # Thêm thông tin kênh
        channel = bot.get_channel(data['channel_id'])
        channel_name = channel.name if channel else "Kênh lạ"
        embed.set_footer(text=f"Tại kênh #{channel_name} • Vị trí: #{index} gần nhất")

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"Lỗi lệnh chaydidau: {e}")
        await ctx.reply("⚠️ Có lỗi xảy ra khi truy xuất dữ liệu.")

# Chạy bot
if TOKEN:
    bot.run(TOKEN)
else:
    print("Chưa tìm thấy TOKEN trong file .env")