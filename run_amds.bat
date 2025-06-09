@echo off
start "Voice Adapter" cmd /k "call conda activate maipet && cd /d C:\GitHub\MaiM-desktop-pet && echo Running Pet Adapter... && python main.py" 