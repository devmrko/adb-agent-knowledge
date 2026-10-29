#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -d .tools/kev/.git ]; then
  git clone https://github.com/jaredpalmer/kev.git .tools/kev
fi
git -C .tools/kev checkout --detach dd375f27fd61486c52204205e10a0d2e10f3b34a
./uvw sync --project .tools/kev --locked --python 3.13 --extra serve
printf '%s\n' 'Kev installed. First run downloads its model: ./scripts/run_kev.sh'
