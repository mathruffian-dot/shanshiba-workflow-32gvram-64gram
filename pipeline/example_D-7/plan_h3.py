"""〈D-7〉H3 逐鏡設定（pipeline_gen.py 匯入）。
lines: (台詞 id, 開始秒數)，對應 voice/<id>.wav。frame：首幀（預設 first/<id>.png）；last：尾幀鎖；native：不給固定音軌（讓 H3 自己出音效，只用在沒有人說話的鏡頭）。"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
STYLE = ("a realistic cinematic live-action Taiwanese film shot on anamorphic lenses, 35mm grain, warm light with drifting dust, "
         "shallow depth of field")
SCHOOL = "a Taiwanese elementary school classroom"
TCH = ("the teacher, a handsome man in black rectangular glasses wearing a tan fabric cougar-head costume hood - a lifeless prop whose sewn "
       "face and eyes never move - and a black zip jacket with red lining")
SUBJ = {
    "shb": dict(key="shb", desc=TCH, voice="a calm, warm adult male voice with a Taiwanese accent"),
    "xw": dict(key="xw", desc="Xiaowen, a neat, serious 11-year-old Taiwanese girl, the class monitor (tidy black high ponytail)",
               voice="a clear, bright 11-year-old girl's voice, serious"),
    "afu": dict(key="afu", desc="Afu, a chubby, good-natured 12-year-old Taiwanese boy (short spiky black hair, round cheeks)",
                voice="a mild, friendly 12-year-old boy's voice, slightly dopey"),
    "ahe": dict(key="ahe", desc="Ahe, a mischievous 12-year-old Taiwanese boy (messy spiky black hair with a cowlick, no glasses)",
                voice="a bright 12-year-old boy's voice"),
}
HOOD = "The cougar hood is a lifeless fabric prop whose sewn face and eyes never move."
ONLY = "Only {who} speaks; every other person keeps their lips closed."
LOCK = "The camera stays locked on the tripod; no zoom, no pan."
ROOM = "Quiet classroom room tone with faint distant school sounds."
RECESS = "Lively classroom recess ambience: kids chatting softly in the background, chairs scraping, distant playground noise."
NIGHT = "Quiet night room tone, a faint distant scooter passing outside."
SILENT = "Near silence: a faint room tone."

SHOTS = []


def S(id, subs, action, lines=(), dur=4.0, frame=None, last=None, cons=(), soundscape=None, setting=SCHOOL, size=(1344, 768), native=False):
    SHOTS.append(dict(id=id, subs=list(subs), action=action, lines=list(lines), dur=dur, frame=frame or id, last=last, cons=list(cons),
                      soundscape=soundscape or ROOM, setting=setting, size=list(size), native=native))


V = (768, 1344)
HOME = "a Taiwanese family apartment at night"
# --- 1 D-7 下課
S("S01", ["shb"], "Students chat during recess; Ahe folds his paper airplane; Afu tears open his snack bag. In the front doorway the teacher lifts "
  "his coffee mug slightly and says his line to the class in a casual, offhand tone.", [("L01", 1.0)], 5.0,
  cons=[HOOD, "Only the teacher in the doorway speaks the line."], soundscape=RECESS)
S("S02", ["xw"], "Xiaowen looks toward the front door and asks her question seriously, her pen still in her hand.", [("L02", 0.6)], 4.0,
  cons=[ONLY.format(who="Xiaowen")], soundscape=RECESS)
S("S03", ["shb"], "The teacher pauses for a beat with a blank face, blinks once, answers with one short word, then turns away toward the corridor.",
  [("L03", 1.5)], 4.0, cons=[HOOD], soundscape=RECESS)
S("S04", ["xw", "ahe", "afu"], "Xiaowen writes neatly in her notebook; Ahe tilts his finished paper airplane proudly; Afu pours the last snacks from "
  "the bag into his mouth and chews happily. Classmates chat behind them.", dur=5.0, native=True,
  soundscape="Lively classroom recess: many kids chatting and laughing softly in the background, chairs scraping, a snack bag rustling, distant playground noise.")
# --- 2 D-7 夜（直式）
S("P1a", ["xw"], "Xiaowen holds her phone flat above her notes and taps the screen to take a photo, then taps once more to send it and puts the "
  "phone down neatly on the desk, satisfied. She does not speak.", dur=6.0, setting=HOME, size=V, soundscape=NIGHT)
S("P1b", ["ahe"], "Ahe plays the handheld game console intensely, thumbs moving quickly, grinning. He does not speak.", dur=6.0, setting=HOME, size=V,
  soundscape=NIGHT)
S("P1c", ["afu"], "Afu shovels rice into his mouth with his chopsticks and chews happily, eyes closing with joy. He does not speak.", dur=6.0,
  setting=HOME, size=V, soundscape=NIGHT)
# --- 3 D-1 放學
S("S05", ["shb"], "The teacher glances at the blank laptop screen, then looks up at the students and says his line calmly.", [("L05", 0.8)], 5.0,
  cons=[HOOD], soundscape="After-school classroom: backpacks zipping, chairs pushed in, kids leaving.")
S("S06", ["ahe"], "Ahe's hands stop on the backpack zipper. He slowly lifts his head, his mouth slowly falling open in shock, and stays frozen. "
  "He does not speak.", dur=4.0, soundscape="After-school classroom: backpacks zipping, chairs pushed in.")
S("N2a", ["xw"], "Xiaowen zips her backpack closed calmly and smiles a little. She does not speak.", dur=4.0, size=V)
S("N2b", ["ahe"], "Ahe stays frozen in shock with his mouth open; only his eyes blink once. He does not speak.", dur=4.0, size=V)
S("N2c", ["afu"], "Afu licks his popsicle happily and swings his backpack onto his shoulder. He does not speak.", dur=4.0, size=V)
# --- 4 阿禾房間
S("S07", ["ahe"], "Ahe takes a deep breath and pushes up his T-shirt sleeves one after the other, keeping his face toward the camera with a "
  "determined look, ending with both fists on the desk. He does not speak.", dur=4.0, setting=HOME, soundscape=NIGHT, last=HERE / "first/S07_end.png",
  cons=["Ahe keeps facing the camera for the whole clip and never looks down; his face, cowlick and messy hair stay exactly the same."])
S("S08", [], "The boy's hand slowly drags the yellow highlighter across the last white line from left to right, turning it yellow. The hand moves "
  "slowly and steadily; the page does not move.", dur=4.0, setting=HOME, native=True,
  soundscape="A felt-tip highlighter squeaking softly across paper in a quiet room at night.")
S("S09", ["ahe"], "Ahe, cheek resting on the yellow textbook, slowly stretches his arm and drags the phone toward himself, eyes half closed. "
  "He does not speak.", dur=5.0, setting=HOME, soundscape=NIGHT)
S("S11", ["ahe"], "Ahe stares at the phone screen, completely frozen; his eyes widen a little more and he blinks once, slowly. He does not speak.",
  dur=4.0, setting=HOME, soundscape=NIGHT)
# --- 5 深夜（直式）
S("P3a", ["xw"], "Xiaowen sleeps peacefully, breathing slowly; the curtain moves gently in the night breeze.", dur=5.0, setting=HOME, size=V,
  soundscape=NIGHT)
S("P3b", ["ahe"], "Ahe clutches his head and rocks slightly back and forth in despair, staring at the yellow textbook. He does not speak.", dur=5.0,
  setting=HOME, size=V, soundscape=NIGHT)
S("P3c", ["afu"], "Afu sleeps hugging the pillow, smacks his lips once and smiles in his sleep.", dur=5.0, setting=HOME, size=V, soundscape=NIGHT)
S("S15", [], "The two hands rest still on the exam paper; nothing else moves except a faint flicker of sunlight.", dur=4.0, native=True,
  soundscape="A quiet exam room: many pencils scratching on paper, a page turning, a clock ticking softly. No voices.")
# --- 6 D-0
S("S12", ["xw", "ahe", "afu"], "Xiaowen keeps turning a pencil in the sharpener and glances at Ahe with a tiny smile; Ahe sits slumped, blinking "
  "slowly with heavy eyes; Afu chews his egg crepe happily. Nobody speaks.", dur=5.5)
S("S13", ["shb"], "The teacher sets his coffee mug down on the desk, then leans forward and places the stack of exam papers down at the bottom "
  "edge of the frame. A thin wisp of steam keeps rising from the paper stack. He does not speak.", dur=5.0, cons=[HOOD])
S("S14", ["afu"], "Afu takes the stack of papers with both hands, says his line cheerfully, then turns slightly to pass the stack back over his "
  "shoulder.", [("L14", 0.8)], 4.5, cons=[ONLY.format(who="Afu")])
S("S16", ["afu"], "Afu stares at the paper; his smile freezes, his eyes slowly widen, and he asks his question in a small, stunned voice.",
  [("L16", 1.0)], 4.0, cons=[ONLY.format(who="Afu")])
S("N3a", ["xw"], "Xiaowen writes steadily and calmly on her exam paper. She does not speak.", dur=4.0, size=V)
S("N3b", ["ahe"], "Ahe writes frantically and wipes the sweat from his forehead with the back of his hand. He does not speak.", dur=4.0, size=V)
S("N3c", ["afu"], "Afu stays frozen staring at the exam paper, then slowly blinks. He does not speak.", dur=4.0, size=V)
# --- 7 段考中
S("S17", ["afu"], "Afu presses his palms flat on the paper, pauses, then looks up toward the front of the room and says his line, puzzled.",
  [("L17", 0.6)], 4.5, cons=[ONLY.format(who="Afu")])
S("S19", ["shb"], "The teacher raises his eyebrows, half-closes his eyes, pushes up his glasses with one finger and says his line flatly.",
  [("L19", 1.2)], 4.0, cons=[HOOD])
S("S20", ["shb"], "The printer keeps pushing freshly printed sheets out into the tray one after another; the teacher gives a huge, long yawn "
  "behind his hand, then rubs one eye. He does not speak.", dur=5.5, setting="a dark school teachers' office at night", native=True, cons=[HOOD],
  soundscape="A laser printer whirring and pages sliding out rhythmically, one long tired yawn, a quiet empty office at night.")
S("S21", ["afu"], "All the classmates write on their papers; Afu keeps his palms flat on the paper, eyes closed, a blissful smile, and says his "
  "line softly and contentedly.", [("L21", 1.6)], 5.0, cons=[ONLY.format(who="Afu")],
  soundscape="Quiet exam room: pencils scratching on paper.")

BY_ID = {s["id"]: s for s in SHOTS}
