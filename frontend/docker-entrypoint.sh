#!/bin/sh
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
npm install
exec npm run dev -- --host 0.0.0.0
