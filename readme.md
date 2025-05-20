Here's a professional README.md in English following your project structure:

```markdown
# 🚗 AutoMaster Bot - Telegram Bot for Auto Repair Shops

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Aiogram](https://img.shields.io/badge/Aiogram-2.x-green.svg)
![OpenAI](https://img.shields.io/badge/OpenAI-ChatGPT-brightgreen.svg)

A comprehensive Telegram bot solution for independent auto mechanics to manage appointments, provide preliminary diagnostics via photo, and answer common questions using AI.

## ✨ Key Features

- **Smart Booking System** with real-time availability
- **Photo Diagnostics** for preliminary assessments
- **AI Assistant** powered by ChatGPT
- **Master Control Panel** via Telegram
- **Automated Notifications** and reminders

## 🛠 Project Structure

```
autorepair-bot/
├── main.py                # Bot entry point
├── config.py              # Configuration and secrets
├── database.py            # SQLite database operations
├── keyboards.py           # Interactive keyboards
├── gpt_helper.py          # ChatGPT integration
├── handlers/              # Message handlers
│   ├── __init__.py
│   ├── common.py          # Basic commands (start, help)
│   ├── booking.py         # Appointment management
│   ├── photo_diagnostic.py # Photo diagnostics
│   └── admin.py           # Master commands
└── utils/                 # Utility modules
    ├── logger.py          # Logging configuration
    ├── notifications.py   # Notification system
    └── storage.py         # Media storage handling
```

## 🚀 Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/autorepair-bot.git
cd autorepair-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

4. Initialize database:
```bash
python database.py
```

5. Start the bot:
```bash
python main.py
```

## 🔧 Configuration

Edit `config.py` for:
- Business hours
- Service offerings
- Pricing
- AI response templates

## 💻 Usage

### For Clients:
- `/start` - Main menu
- "📅 Book Appointment" - Schedule service
- "📸 Photo Diagnostics" - Submit issue photos
- "❓ Quick Question" - Get AI-assisted answer

### For Master:
- `/schedule` - View appointments
- `/today` - Today's workload
- `/stats` - Business statistics
- `/notify` - Send broadcast message

## 🤖 AI Integration

The bot uses ChatGPT for:
- Answering technical questions
- Generating preliminary diagnostics
- Providing service explanations

Example implementation:
```python
# gpt_helper.py
async def get_ai_response(question: str) -> str:
    """Get vehicle-specific advice from ChatGPT"""
    prompt = f"As an auto mechanic, respond to this car question: {question}"
    return await openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
```

## 📈 Roadmap

- [ ] Payment integration
- [ ] Customer loyalty system
- [ ] Advanced analytics dashboard
- [ ] Multi-language support

## 🤝 Contributing

1. Fork the project
2. Create your feature branch
3. Submit a pull request

## 📜 License

MIT - See [LICENSE](LICENSE) for details