@echo off

echo Installing requirements

pip install -r requirements.txt

cls

echo Assuming successful installation, starting Checker.py in 2 seconds

timeout /t 2

py Checker.py 
