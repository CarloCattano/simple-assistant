Learning exercise by integrating GEMMINI and/or OLLAMA self hosted.
Tool usage integration and telegram interface

### Features:
- Chat with llm in /text or /audio assistant, also with voice notes with tts stt.
- Forward a message and transcribe the text to audio, or use it as a prompt
- Simple web scraping agentic tools (WIP)
- Context Storage ( needs encription probably, or proper db ) 


### Usage:
use the provided ```.env.template``` and fill in your ```GEMINI_API_KEY=``` and ```TELEGRAM_BOT_TOKEN=```

Choose an llm provider (Gemini or local):
- ```gemini``` or ```ollama``` in the .env file under ```LLM_PROVIDER=```

```ADMIN_ID``` is your telegram ID, for now nothing is restricted but this is one way to start.

Rename the file to .env
```bash
mv .env.template .env
```

Make a virtual environment, install requirements and run:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py

```




#### TODO's 
    - [x] Add context with previous messages
    - [ ] pass scrape tool output to prompt
    - UX 

    
![image](https://github.com/user-attachments/assets/6bc2f7fd-0f9b-472c-8f47-03a607a7a11f)
