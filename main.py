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
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['discord_bot_db'] 
logs_collection = db['message_logs'] 

# 3. Cấu hình Bot Discord
intents = discord.Intents.default()
intents.message_content = True  
intents.members = True          

bot = commands.Bot(command_prefix='!', intents=intents)

# Hàm phụ trợ: Lấy danh sách URL từ attachments
def get_attachments_data(message):
    attachment_urls = []
    if message.attachments:
        for attachment in message.attachments:
            attachment_urls.append({
                'url': attachment.url,
                'filename': attachment.filename,
                'content_type': attachment.content_type # image/png, audio/mpeg, etc.
            })
    return attachment_urls

# --- Sự kiện: Bot đã sẵn sàng ---
@bot.event
async def on_ready():
    print(f'✅ Bot đã đăng nhập với tên: {bot.user.name}')
    print('🚀 Đang theo dõi tin nhắn (Text, Ảnh, Audio)...')

# --- Sự kiện: Tin nhắn bị XÓA ---
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return

    # Lấy thông tin file đính kèm (nếu có)
    attachments = get_attachments_data(message)

    # Nếu không có nội dung text VÀ không có file đính kèm thì bỏ qua
    if not message.content and not attachments:
        return

    log_entry = {
        'message_id': message.id,
        'author_id': message.author.id,
        'author_name': message.author.name,
        'author_avatar': message.author.display_avatar.url, # Lưu thêm avatar để hiển thị cho đẹp
        'content_before': message.content,
        'content_after': None,
        'attachments': attachments, # Lưu danh sách file
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
    if before.author.bot:
        return
    
    # Kiểm tra xem nội dung HOẶC file đính kèm có thay đổi không
    # (Thường edit chỉ đổi text, nhưng cứ lưu lại attachments của bản gốc cho chắc)
    if before.content == after.content:
        return

    attachments = get_attachments_data(before)

    log_entry = {
        'message_id': before.id,
        'author_id': before.author.id,
        'author_name': before.author.name,
        'author_avatar': before.author.display_avatar.url,
        'content_before': before.content,
        'content_after': after.content,
        'attachments': attachments,
        'type': 'EDIT',
        'channel_id': before.channel.id,
        'created_at': datetime.now(timezone.utc)
    }

    try:
        logs_collection.insert_one(log_entry)
    except Exception as e:
        print(f"Lỗi lưu DB (Edit): {e}")

# --- Lệnh: !chaydidau ---
@bot.command(name='chaydidau')
async def chaydidau(ctx, member: discord.Member = None, index: int = 1):
    if member is None:
        await ctx.reply("Sai cú pháp! Vui lòng dùng: `!chaydidau <@tag> <số thứ tự>`")
        return
    
    if index < 1:
        index = 1

    try:
        cursor = logs_collection.find({'author_id': member.id})\
                                .sort('created_at', -1)\
                                .skip(index - 1)\
                                .limit(1)
        
        result = list(cursor)

        if not result:
            await ctx.reply(f"Không tìm thấy tin nhắn đã xóa/sửa thứ #{index} nào của **{member.display_name}**.")
            return

        data = result[0]
        
        # Setup màu sắc và tiêu đề
        embed_color = discord.Color.red() if data['type'] == 'DELETE' else discord.Color.orange()
        title_type = "ĐÃ XÓA" if data['type'] == 'DELETE' else "ĐÃ CHỈNH SỬA"
        
        embed = discord.Embed(
            description=f"**Tác giả:** {member.mention}",
            color=embed_color,
            timestamp=data['created_at']
        )
        embed.set_author(name=f"{data['author_name']} - {title_type}", icon_url=data.get('author_avatar', ''))

        # Hiển thị nội dung Text
        if data['type'] == 'EDIT':
            embed.add_field(name="Trước khi sửa:", value=data['content_before'] or "_[Không có nội dung text]_", inline=False)
            embed.add_field(name="Sau khi sửa:", value=data['content_after'] or "_[Không có nội dung text]_", inline=False)
        else:
            embed.add_field(name="Nội dung:", value=data['content_before'] or "_[Chỉ có file đính kèm]_", inline=False)

        # --- Xử lý File đính kèm (Ảnh / Âm thanh) ---
        attachments = data.get('attachments', [])
        image_set = False # Cờ kiểm tra xem đã set ảnh nền cho embed chưa

        if attachments:
            file_links = []
            for att in attachments:
                url = att['url']
                filename = att['filename']
                ctype = att.get('content_type', '')

                # Tạo link markdown
                link_text = f"[{filename}]({url})"
                file_links.append(link_text)

                # Nếu là ảnh và chưa set ảnh nền -> Set ảnh đầu tiên làm hình to
                if not image_set and ctype and 'image' in ctype:
                    embed.set_image(url=url)
                    image_set = True
            
            # Liệt kê tất cả các link file vào một field
            embed.add_field(name="Tệp đính kèm:", value="\n".join(file_links), inline=False)

        # Thông tin footer
        channel = bot.get_channel(data['channel_id'])
        channel_name = channel.name if channel else "Kênh lạ"
        embed.set_footer(text=f"Tại kênh #{channel_name} • Vị trí: #{index}")

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"Lỗi lệnh chaydidau: {e}")
        await ctx.reply("⚠️ Có lỗi xảy ra khi truy xuất dữ liệu.")

if TOKEN:
    bot.run(TOKEN)
else:
    print("Chưa tìm thấy TOKEN trong file .env")

