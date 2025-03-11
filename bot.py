import os
import json
import aiohttp
import asyncio
import logging
import sys
import subprocess
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("7818348226:AAH08AaePMIRgvRwKKZuZCMOhub69nG1txk")
ADMIN_ID = int(os.getenv("6186511950"))
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# Dictionary to store user session data
user_sessions = {}
premium_users = {}

# ------------------- GitHub Authentication -------------------
async def get_github_access_token(code):
    try:
        url = "https://github.com/login/oauth/access_token"
        payload = {
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code
        }
        headers = {"Accept": "application/json"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, headers=headers) as response:
                return await response.json()
    except Exception as e:
        logging.error(f"GitHub Auth Error: {e}")
        return None

async def get_user_repos(access_token):
    try:
        url = "https://api.github.com/user/repos"
        headers = {"Authorization": f"token {access_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                return await response.json()
    except Exception as e:
        logging.error(f"GitHub Repo Fetch Error: {e}")
        return []

# ------------------- Bot Commands -------------------
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    try:
        login_url = f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}&scope=repo"
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Login with GitHub", url=login_url)
        )
        await message.reply("Welcome! Please login with GitHub to continue.", reply_markup=keyboard)
    except Exception as e:
        logging.error(f"Start Command Error: {e}")

@dp.message_handler(commands=['buy'])
async def buy_cmd(message: types.Message):
    await message.reply("Premium Price: $5/month\nDM @Gamenter to purchase.")

@dp.message_handler(commands=['addpremium'])
async def add_premium_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("Only the admin can add premium users.")

    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: /addpremium <user_id>")

    try:
        user_id = int(args[1])
        premium_users[user_id] = True
        await message.reply(f"User {user_id} is now a premium user!")
    except Exception as e:
        logging.error(f"Add Premium Error: {e}")
        await message.reply("Error adding premium user.")

@dp.message_handler(commands=['repos'])
async def repos_cmd(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        return await message.reply("You need to log in first using /start.")

    access_token = user_sessions[user_id]
    repos = await get_user_repos(access_token)

    if not repos:
        return await message.reply("No repositories found.")

    keyboard = InlineKeyboardMarkup()
    for repo in repos:
        keyboard.add(InlineKeyboardButton(repo['name'], callback_data=f"deploy:{repo['full_name']}"))

    await message.reply("Select a repository to deploy:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("deploy:"))
async def deploy_repo(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    repo_name = callback_query.data.split(":")[1]

    if user_id in premium_users:
        max_repos = 5
    else:
        max_repos = 1

    if len(user_sessions.get(user_id, [])) >= max_repos:
        return await bot.send_message(user_id, f"You can only deploy {max_repos} repositories.")

    try:
        repo_url = f"https://github.com/{repo_name}.git"
        os.system(f"git clone {repo_url} user_repos/{repo_name}")

        user_sessions.setdefault(user_id, []).append(repo_name)
        await bot.send_message(user_id, f"Repository {repo_name} deployed successfully!")
    except Exception as e:
        logging.error(f"Deployment Error: {e}")
        await bot.send_message(user_id, "Deployment failed.")

@dp.message_handler(commands=['stop'])
async def stop_cmd(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_sessions or not user_sessions[user_id]:
        return await message.reply("You have no active deployments.")

    repo_name = user_sessions[user_id][-1]
    
    try:
        os.system(f"rm -rf user_repos/{repo_name}")
        user_sessions[user_id].remove(repo_name)
        await message.reply(f"Repository {repo_name} stopped.")
    except Exception as e:
        logging.error(f"Stop Command Error: {e}")
        await message.reply("Error stopping repository.")

@dp.message_handler(commands=['status'])
async def status_cmd(message: types.Message):
    user_id = message.from_user.id
    deployed_repos = user_sessions.get(user_id, [])

    if not deployed_repos:
        return await message.reply("No active deployments.")

    await message.reply(f"Your active repositories:\n" + "\n".join(deployed_repos))

# ------------------- Install Python Packages -------------------
@dp.message_handler(commands=['install'])
async def install_package(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ Only the admin can install packages.")

    args = message.text.split()
    if len(args) < 2:
        return await message.reply("Usage: `/install package_name`", parse_mode="Markdown")

    package_name = args[1]
    
    try:
        process = subprocess.run([sys.executable, "-m", "pip", "install", package_name], capture_output=True, text=True)
        if process.returncode == 0:
            await message.reply(f"✅ Successfully installed `{package_name}`", parse_mode="Markdown")
        else:
            await message.reply(f"❌ Installation failed:\n```\n{process.stderr}\n```", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Package Installation Error: {e}")
        await message.reply("❌ An error occurred while installing the package.")

# ------------------- Auto Restart Function -------------------
async def restart_bot():
    logging.info("Bot restarting...")
    os.execv(sys.executable, ['python'] + sys.argv)

async def bot_crash_handler():
    while True:
        try:
            await dp.start_polling()
        except Exception as e:
            logging.error(f"Bot Crashed: {e}")
            await asyncio.sleep(5)  # Wait before restarting
            await restart_bot()

# ------------------- Run Bot -------------------
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_crash_handler())
