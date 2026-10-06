"""〈D-7〉首幀：python gen_frames.py [ids...] [--force]。Image 2.5（medium、n=1），3 路並行。
輸出 first/<id>.png（舊圖移到 first/old/）。教室鏡構圖依 blender/layouts/L_<id>.png（已鏡射：窗在學生左手邊）。
直式三分割小格（P*/N*）用 768x1344。先跑房間母版 ROOM_AH ROOM_XW，再跑用到它們的鏡頭。"""
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, r"C:\AI\tools")
import img25

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CH = ROOT / "角色資產/老師這次換你"
OUT = HERE / "first"; OLD = OUT / "old"
OUT.mkdir(exist_ok=True); OLD.mkdir(exist_ok=True)
FORCE = "--force" in sys.argv
PORTRAIT = "768x1344"

REF = {"T": CH / "老師_山獅霸/01_定妝照.png", "XW": CH / "班長小雯/01_定妝照.png", "AH": CH / "阿禾/01_定妝照.png",
       "AF": CH / "阿福/01_定妝照.png", "RB": CH / "教室/從後方.png", "RF": CH / "教室/從前方.png",
       "RAH": OUT / "ROOM_AH.png", "RXW": OUT / "ROOM_XW.png"}
KEEP = {
    "T": "Keep EXACTLY the same man as Image {n} (the teacher): black rectangular glasses, plain solid tawny cougar-head fabric hood with rounded ears worn on his head (a lifeless prop, no stripes, no spots, no mane), black zip jacket with red lining, white T-shirt. ",
    "XW": "Keep EXACTLY the same girl as Image {n} (Xiaowen): round, clearly 11-12 year-old child's face, tidy black high ponytail. She must look like a child, never like a teenager. ",
    "AH": "Keep EXACTLY the same boy as Image {n} (Ahe): same face, messy spiky black hair with a cowlick sticking up at the crown, cheeky face. No glasses. ",
    "AF": "Keep EXACTLY the same boy as Image {n} (Afu): same face, round cheeks, short spiky black hair, chubby build. ",
    "RB": "The classroom is exactly that of Image {n} (green chalkboard, round wall clock, big windows with cream curtains on the LEFT as seen from the back of the room, wooden desks). ",
    "RF": "The classroom is exactly that of Image {n} seen from the FRONT of the room (windows with cream curtains on the RIGHT, cork board and bookshelves at the back, wooden desks). ",
    "RAH": "The bedroom is exactly the room of Image {n} (Ahe's bedroom: same desk, lamp, bed and window). ",
    "RXW": "The bedroom is exactly the room of Image {n} (Xiaowen's bedroom: same tidy desk, lamp, bed and wall chart). ",
}
SCHOOL = {"XW": "She wears the white short-sleeve school shirt and brown pleated skirt. ",
          "AH": "He wears the white short-sleeve school shirt and brown shorts. ",
          "AF": "He wears the white short-sleeve school shirt and brown shorts. "}
HOME = {"XW": "At home she wears light lavender pajamas, hair still in its high ponytail. ",
        "AH": "At home he wears a plain navy-blue T-shirt. ",
        "AF": "At home he wears a plain mustard-yellow T-shirt. "}
UNIFORM = ("Every student wears the same plain WHITE short-sleeve school shirt of a Taiwanese elementary school - no vests, no ties, no blazers, "
           "no hoodies, no coloured clothes; they are 11-12 year-old children. ")
NOTEXT = "No captions, no readable text anywhere: nothing written on the chalkboard, no letters on any paper, book, screen or poster (only tiny blurred grey lines). "
CINE = ("Cinematic film still, shot on anamorphic lenses, 35mm film grain, shallow depth of field with creamy bokeh, dramatic lighting: "
        "{light}, teal-and-orange colour grade, gentle vignette, high contrast, like a scene from a Taiwanese feature film - NOT a bright flat TV look. "
        "{fmt}, the picture fills the ENTIRE frame edge to edge - NO black letterbox bars, NO black borders. ")
LAYOUT = ("The LAST image is only a framing guide made of grey box figures (black box = the teacher, pink = Xiaowen, blue = Ahe, orange = Afu): "
          "copy its camera position, angle and where people sit or stand, but never its blocky look. ")
L_RECESS = "warm golden afternoon sunlight streaming through the classroom windows with floating dust in the light beams"
L_DUSK = "warm orange late-afternoon sunset light low through the windows, long shadows"
L_LAMP = "a single warm desk lamp in a dark bedroom at night, deep blue shadows"
L_MOON = "soft cool blue moonlight through thin curtains in a dark bedroom at night"
L_MORN = "soft morning light with gentle golden sun rays through the windows, calm and quiet"
L_OFFICE = "a single warm desk lamp in a dark office at night, the cold blue glow of a printer's status light"
L_DINNER = "warm cosy yellow home dining-room light in the evening"

# id: (refs, light, body, extra)   extra: dict(size=..., home=bool)
SHOTS = {
    "ROOM_AH": ([], L_LAMP, "A small, slightly messy Taiwanese 12-year-old boy's bedroom at night, empty, no people: a study desk against the wall under a "
                "window with a desk lamp switched on, piles of textbooks and handouts, a single bed with a rumpled blue blanket along the other wall, "
                "a handheld game console on the bed, a soccer ball on the floor, a couple of posters without readable text.", {}),
    "ROOM_XW": ([], L_LAMP, "A very neat, tidy Taiwanese 11-year-old girl's bedroom at night, empty, no people: a clean study desk with a desk lamp switched "
                "on, pens arranged in a cup, a colourful study-plan chart with a grid of little coloured squares pinned on the wall above the desk, a single "
                "bed with a neatly tucked pastel-pink blanket, a few soft toys on a shelf.", {}),
    # ---------------- 1 D-7 下課
    "S01": (["T", "XW", "AH", "AF", "RB"], L_RECESS,
            "Wide shot from the back corner of the classroom during recess (break time), the room lively: students chat in small groups at their desks. "
            "Front row: Ahe at the middle desk folding a paper airplane; Afu one row behind him on the window side opening a bag of snacks; Xiaowen at "
            "the front-row desk on the corridor side with an open notebook. At the front of the room on the RIGHT side (corridor side), the teacher "
            "stands in the open front doorway holding a white coffee mug, looking into the room. Windows on the LEFT of the frame.", {}),
    "S02": (["XW", "RF"], L_RECESS,
            "Medium shot, waist up, of Xiaowen - a small 11-year-old CHILD with a round childish face, not a teenager - sitting at her front-row desk, an open notebook and a pen in front of her; she has just looked up toward "
            "the front of the room (frame left) with a serious, attentive face. Behind her the classmates chat during recess, softly blurred.", {"school": True}),
    "S03": (["T", "RB"], L_RECESS,
            "Seen from the students' seats looking toward the FRONT of the room. Medium shot, waist up, of the teacher standing in the open front doorway right next to the green chalkboard (the chalkboard is beside/behind him, NOT a cork board or bookshelves), holding a white coffee mug in one hand, looking toward "
            "the students with a calm, slightly blank face, as if he has just been asked something. The bright school corridor behind him.", {}),
    "S04": (["XW", "AH", "AF", "RF"], L_RECESS,
            "Front view from the teacher's desk toward the front rows during recess. Xiaowen sits in the LEFT third of the frame at her front-row desk, "
            "writing neatly in a notebook. Ahe sits in the CENTER third at the middle front-row desk, holding up a finished paper airplane with a grin. "
            "Afu sits in the RIGHT third, one row behind, tipping a bag of snacks toward his open mouth. The three are clearly separated, each inside "
            "their own third of the frame, all waist-up and well lit. Classmates chat behind them.", {"school": True}),
    # ---------------- 2 D-7 夜（直式三格）
    "P1a": (["XW", "RXW"], L_LAMP,
            "Vertical portrait framing, waist up. At night Xiaowen sits at her tidy study desk under the warm desk lamp, holding her smartphone flat "
            "above her neatly written notes to take a photo of them, focused and calm; the colourful study-plan chart on the wall behind her.",
            {"size": PORTRAIT, "home": True}),
    "P1b": (["AH", "RAH"], L_LAMP,
            "Vertical portrait framing. At night Ahe lies on his back on his bed holding a handheld game console above his face with both hands, "
            "grinning, totally absorbed, the screen glow on his face.", {"size": PORTRAIT, "home": True}),
    "P1c": (["AF"], L_DINNER,
            "Vertical portrait framing, waist up. In the evening at home Afu sits at the dining table holding a huge bowl of rice heaped with food, "
            "chopsticks in hand, cheeks full, blissfully happy.", {"size": PORTRAIT, "home": True}),
    # ---------------- 3 D-1 放學
    "S05": (["T", "RF"], L_DUSK,
            "Medium shot, after school: the teacher sits behind the teacher's desk at the front of the classroom, the chalkboard behind him. An open "
            "laptop stands on the desk, angled so its bright, completely BLANK white screen is partly visible to the camera; the white glow lights his "
            "face from below. He looks up toward the students.", {}),
    "S06": (["AH", "RF"], L_DUSK,
            "Medium shot, waist up, of Ahe at his front-row desk after school, his school backpack on the desk, both hands on the backpack zipper, "
            "half-zipped. He is frozen mid-motion, head lifting, mouth starting to fall open in shock. Classmates behind him putting on backpacks.",
            {"school": True}),
    "N2a": (["XW", "RF"], L_DUSK,
            "Vertical portrait framing, waist up. After school in the classroom, Xiaowen calmly closes the zipper of her neat backpack on her desk, "
            "composed and relaxed, a small satisfied face.", {"size": PORTRAIT, "school": True}),
    "N2b": (["AH", "RF"], L_DUSK,
            "Vertical portrait framing, waist up. After school in the classroom, Ahe stands frozen holding his backpack zipper, eyes wide, mouth "
            "open in shock, as if he just heard terrible news.", {"size": PORTRAIT, "school": True}),
    "N2c": (["AF", "RF"], L_DUSK,
            "Vertical portrait framing, waist up. After school in the classroom, Afu happily licks a popsicle while lazily slinging his backpack over "
            "one shoulder, carefree.", {"size": PORTRAIT, "school": True}),
    # ---------------- 4 阿禾房間 深夜
    "S07": (["AH", "RAH"], L_LAMP,
            "Medium shot at night in Ahe's bedroom: Ahe sits at his study desk facing the camera, a huge messy tower of textbooks and handouts piled "
            "in front of him under the desk lamp. He is taking a deep breath, pushing up the sleeve of his T-shirt, determined.", {"home": True}),
    "S08": ([], L_LAMP,
            "Close-up looking down at an open textbook on a desk under warm lamp light: EVERY line on both pages is already covered in bright "
            "fluorescent-yellow highlighter, the whole page glowing yellow, except the very last line at the bottom of the right page which is still "
            "white. A boy's hand holds a yellow highlighter pen at the start of that last white line. The printed lines are tiny blurred grey marks.", {}),
    "S09": (["AH", "RAH"], L_LAMP,
            "Medium shot late at night: Ahe is slumped forward with his cheek resting on an open textbook whose pages are completely bright yellow "
            "with highlighter, eyes half closed, exhausted, one arm stretched out reaching for a smartphone lying face-down on the desk. Piles of "
            "books around, desk lamp on.", {"home": True}),
    "S11": (["AH"], "the cold blue-white glow of a phone screen as the only light in a dark room at night",
            "Close-up of Ahe's face in a dark bedroom, lit only by the glow of a smartphone he holds up in front of him (we see only the back of the "
            "phone at the bottom edge of the frame), eyes wide, mouth slightly open, completely stunned.", {"home": True}),
    # ---------------- 5 深夜（直式三格）
    "P3a": (["XW", "RXW"], L_MOON,
            "Vertical portrait framing. Late at night Xiaowen sleeps peacefully on her back in her bed, the pastel blanket tucked neatly up to her "
            "chest, a calm face, the desk lamp switched off.", {"size": PORTRAIT, "home": True}),
    "P3b": (["AH", "RAH"], L_LAMP,
            "Vertical portrait framing, waist up. Late at night Ahe sits at his desk under the lamp, clutching his head with both hands, staring "
            "desperately at a completely yellow highlighted textbook, hair messier than ever.", {"size": PORTRAIT, "home": True}),
    "P3c": (["AF"], L_MOON,
            "Vertical portrait framing. Late at night Afu sleeps deeply on his side in bed hugging a big pillow, mouth open with a little drool, "
            "a peaceful happy face, dark bedroom.", {"size": PORTRAIT, "home": True}),
    # ---------------- 6 D-0 早自習
    "S12": (["XW", "AH", "AF", "RF"], L_MORN,
            "Front view from the teacher's desk toward the front rows on an early exam morning, classmates seated quietly at their desks. Xiaowen sits "
            "in the LEFT third at her front-row desk, sharpening a pencil with a small handheld sharpener, five sharpened pencils lined up perfectly on "
            "her desk, glancing sideways at Ahe with a tiny smile. Ahe sits in the CENTER third at the middle front-row desk, slumped, very dark eye "
            "bags, a bright fluorescent-yellow highlighter streak across his cheek. Afu sits in the RIGHT third one row behind, happily biting into a "
            "rolled Taiwanese egg crepe in a paper bag. Each of the three inside their own third of the frame.", {"school": True}),
    "S13": (["T", "RB"], L_MORN,
            "Seen from the students' seats looking toward the FRONT of the room, the green chalkboard directly behind him. Medium shot: the teacher stands behind the teacher's desk at the front of the classroom, eyes a little red and tired. He holds a thick "
            "stack of plain white exam papers against his chest with one arm and a coffee mug in the other hand. A faint wisp of white steam rises from "
            "the TOP of the paper stack itself (not from the mug, the mug does not steam).", {}),
    "S14": (["AF", "RF"], L_MORN,
            "Medium shot of Afu seated at his desk on exam morning: the classmate in the seat in front of him (seen from behind, partly out of frame) "
            "holds a small stack of plain white exam papers back over her shoulder toward Afu; Afu, smiling cheerfully, reaches for it with both hands. "
            "Classmates seated quietly facing the front.", {"school": True}),
    "S15": ([], L_MORN,
            "Close-up looking straight down at a single exam paper lying on a wooden school desk: at the top a large EMPTY white header box with "
            "nothing written in it, below it rows of tiny blurred grey printed lines; a chubby child's two bare hands and bare forearms (short-sleeved white shirt, no long sleeves) rest at the bottom edge of the paper. Nothing else on the desk except one pencil.", {}),
    "S16": (["AF", "RF"], L_MORN,
            "Medium close-up of Afu at his desk holding an exam paper up in both hands, his cheerful smile frozen on his face, eyes beginning to widen "
            "in dawning realisation. Classmates seated behind him.", {"school": True}),
    "N3a": (["XW", "RF"], L_MORN,
            "Vertical portrait framing, waist up. During the exam Xiaowen writes calmly and confidently on her exam paper, back straight, focused.",
            {"size": PORTRAIT, "school": True}),
    "N3b": (["AH", "RF"], L_MORN,
            "Vertical portrait framing, waist up. During the exam Ahe writes frantically on his exam paper, very dark eye bags, a yellow highlighter "
            "streak on his cheek, sweating.", {"size": PORTRAIT, "school": True}),
    "N3c": (["AF", "RF"], L_MORN,
            "Vertical portrait framing, waist up. During the exam Afu holds his exam paper in both hands, frozen, eyes wide, mouth open in shock.",
            {"size": PORTRAIT, "school": True}),
    # ---------------- 7 段考中
    "S17": (["AF", "RF"], L_MORN,
            "Medium close-up of Afu at his desk with both palms laid flat on the exam paper in front of him, a puzzled look, glancing up toward the "
            "front of the room. Classmates writing around him.", {"school": True}),
    "S19": (["T", "RB"], L_MORN,
            "Seen from the students' seats looking toward the FRONT of the room, the green chalkboard directly behind him (no students behind him). Medium close-up of the teacher standing at the front behind the desk, coffee mug in one hand, eyebrows raised, eyes half-closed, lips "
            "pressed into a resigned little smile - a 'here we go again' look - one finger of the other hand pushing up his glasses.", {}),
    "S20": (["T"], L_OFFICE,
            "Medium shot, in the middle of the night in a dark school teachers' office: only one desk lamp is on. The teacher stands beside a big "
            "office laser printer that is printing, freshly printed plain white exam papers sliding out into the tray, a tall stack next to it. He is "
            "in the middle of a huge yawn, one hand covering his mouth. Rows of empty desks fade into darkness behind.", {}),
    "S21": (["AF", "RF"], L_MORN,
            "Medium shot of Afu during the exam: all the classmates around him bend over their papers writing; Afu instead has both palms pressed flat "
            "on his exam paper, eyes closed, a blissful content smile, as if warming his hands by a fire.", {"school": True}),
}


def prompt(sid):
    refs, light, body, ex = SHOTS[sid]
    head = "".join(KEEP[k].format(n=i) for i, k in enumerate(refs, 1))
    kids = [k for k in refs if k in ("XW", "AH", "AF")]
    if ex.get("school") or any(r in refs for r in ("RB", "RF")):
        head += "".join(SCHOOL[k] for k in kids)
    if ex.get("home"):
        head += "".join(HOME[k] for k in kids)
    room = UNIFORM if any(k in refs for k in ("RB", "RF")) else ""
    lay = LAYOUT if (HERE / f"blender/layouts/L_{sid}.png").exists() else ""
    fmt = "Vertical 9:16 portrait image" if ex.get("size") == PORTRAIT else "16:9"
    return head + CINE.format(light=light, fmt=fmt) + NOTEXT + room + lay + body


def one(sid):
    dst = OUT / f"{sid}.png"
    if dst.exists() and not FORCE:
        return sid, "skip"
    if dst.exists():
        shutil.move(str(dst), str(OLD / f"{sid}_{int(time.time())}.png"))
    lay = HERE / f"blender/layouts/L_{sid}.png"
    refs = [REF[k] for k in SHOTS[sid][0]] + ([lay] if lay.exists() else [])
    size = SHOTS[sid][3].get("size", img25.SIZE)
    err = ""
    for _ in range(3):
        try:
            f = (img25.edit(prompt(sid), refs, OUT / "raw" / sid, n=1, size=size) if refs else img25.generate(prompt(sid), OUT / "raw" / sid, n=1, size=size))[0]
            shutil.copyfile(f, dst)
            return sid, "ok"
        except Exception as e:
            err = str(e)[:300]; time.sleep(10)
    return sid, "FAIL " + err


if __name__ == "__main__":
    ids = [a for a in sys.argv[1:] if not a.startswith("--")] or [k for k in SHOTS if not k.startswith("ROOM")]
    with ThreadPoolExecutor(3) as ex:
        for sid, st in ex.map(one, ids):
            print(sid, st, flush=True)
