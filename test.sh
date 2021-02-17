#!/bin/sh
set -e

pip install pydantic

basedir=$(dirname "$0")
workdir=$(mktemp -d)
cleanup(){
  rm -rf $workdir
}
trap cleanup EXIT

echo -n "Test 1: single non-greedy model"
python $basedir/generate.py Offer > $workdir/single_non_greedy.py
python $workdir/single_non_greedy.py
echo ": pass"

echo -n "Test 2: multiple non-greedy models"
python $basedir/generate.py Product Offer QuantitativeValue > $workdir/multiple_non_greedy.py
python $workdir/multiple_non_greedy.py
echo ": pass"

echo -n "Test 3: single greedy model"
python $basedir/generate.py Offer > $workdir/single_greedy.py
python $workdir/single_greedy.py
echo ": pass"

echo -n "Test 4: all models"
python $basedir/generate.py all > $workdir/all.py
python $workdir/all.py
echo ": pass"