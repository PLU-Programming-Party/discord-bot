# Programming Party Discord Bot

Discord bot that allows students to request modifications to the Programming Party website through natural language prompts in Discord.

## Features

- **Discord Integration**: Responds to messages in a Discord channel
- **AI-Powered**: Uses Claude to understand requests and generate CSS/HTML changes
- **GitHub Integration**: Automatically commits and pushes changes to the website repo
- **Real-time Updates**: Website updates via GitHub Actions

## Setup

See `SETUP.md` for deployment instructions.

## Environment Variables

Required variables in `.env`:
- `DISCORD_TOKEN` - Discord bot token
- `DISCORD_CHANNEL_ID` - Channel ID where bot listens
- `CLAUDE_API_KEY` - Anthropic API key
- `GITHUB_TOKEN` - GitHub token with repo write access
- `GITHUB_REPO_OWNER` - Website repo owner
- `GITHUB_REPO_NAME` - Website repo name
- `GITHUB_USER_EMAIL` - Email for git commits
- `GITHUB_USER_NAME` - Name for git commits
- `REPO_LOCAL_PATH` - Local path to cloned website repo

## Running Locally

```bash
pip install -r requirements.txt
python main.py
```

## Deployment

Deploy on Railway:
1. Create a Railway project
2. Connect this GitHub repo
3. Add environment variables
4. Railway will auto-detect Procfile and deploy as a worker
