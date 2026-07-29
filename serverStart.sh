pm2 start uv --name ai-fight-game --cwd /path/to/AIfightArena -- run python -m game_app.server

pm2 start uv --name ai-fight-lobby --cwd /path/to/AIfightArena -- run python -m web_app.server
