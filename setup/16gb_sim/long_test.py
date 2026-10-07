"""長鏡頭補測：python long_test.py A|C  （〈拿下頭套的人〉S34，10.8 秒、260 格，改用 DMAD）"""
import sys
import run_test as R
R.FILM = R.ROOT / "短片" / "三師爸的多重宇宙_20261004" / "h3"
R.SHOTS = [("S34", "S34_a0", "長鏡頭 260 格（10.8 秒）")]
R.main(sys.argv[1], "_long")
