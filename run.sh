#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Xbox 360 Wireless + kernel 6.17+: корректный D-pad для SDL/pygame
export SDL_GAMECONTROLLERCONFIG="${SDL_GAMECONTROLLERCONFIG:-0300a81c5e040000a102000000010000,X360 Wireless Controller,a:b0,b:b1,x:b2,y:b3,back:b6,guide:b8,start:b7,leftshoulder:b4,rightshoulder:b5,leftstick:b9,rightstick:b10,lefttrigger:a2,righttrigger:a5,leftx:a0,lefty:a1,rightx:a3,righty:a4,dpup:b11,dpdown:b12,dpleft:b13,dpright:b14,platform:Linux,}"

if [[ ! -d .venv ]]; then
  python3.12 -m venv --system-site-packages .venv
  .venv/bin/pip install -q -r requirements.txt
fi

exec .venv/bin/python3 gamepad_tester.py "$@"
