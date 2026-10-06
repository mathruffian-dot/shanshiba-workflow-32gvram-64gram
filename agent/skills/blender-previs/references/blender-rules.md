# Blender 規則（本專案實測過的作法）

## 前置

- Blender 需**使用者手動**開啟，並在 3D 視窗按 `N` → **MCP for Blender** → **Start MCP Server**。沒開就會得到 `Could not connect to Blender`。
- 本機版本：Blender 5.2.1 LTS、外掛 v1.7、protocol 7（以 `get_addon_status` 實際回報為準，不要相信目錄名稱）。
- ⚠️ **此 MCP 讓 agent 在 Blender 內執行任意 Python**。動手前先 `get_scene_info()` 確認**當下**檔案，不要把使用者的工作覆蓋掉。
- 操作完用 `get_viewport_screenshot()` 確認結果。

## 角色 proxy

- **方塊人／簡化人形優於精緻人偶**；形狀越陽春，模型的「代理感」越好被忽略。
- 命名：`V5_<角色>_<部位>`（例 `V5_teacher_torso`、`V5_friend_head`），相機 `V5_<鏡號>`，場景物件一律加前綴，避免與舊素材混在一起。
- 用 `object.color` 平塗色區分角色（老師深色、朋友橄欖綠），**不要**花時間做材質。
- 道具（碗、盤、筷子、手機、紙張）也要有，因為它們是**空間錨點**；但畫面中要讀的文字一律留後製。

### 空景鏡

空景（無人）鏡要隱藏角色，但**保留道具**。這在渲染流程逐鏡設定，**不要寫死在場景存檔裡**——否則下一個人打開只看到空房間。

```python
for o in sc.objects:
    if any(o.name.startswith("V5_"+p) for p in ("teacher_", "friend_")) \
       and not any(k in o.name for k in ("bowl", "plate", "chopsticks")):
        o.hide_render = True
```

## 算圖設定

- 引擎：`BLENDER_WORKBENCH`（不需要燈光，最快）。
- `sc.display.shading.color_type='OBJECT'`、`light='STUDIO'`、開啟 shadows 與 cavity。
- `image_settings.file_format='PNG'`、`color_mode='RGB'`。
- 解析度：正式編輯用 1536×864；**布置圖檢查用 960×540**；**guide 影片用 512×288**。

**Workbench 是空間與構圖檢查，不是最終風格參考。**

## 布置圖檢查（生成前必做）

對每個鏡號切換相機各算一張，再合成宮格圖。

| 實測數據 | 值 |
|:---|:---|
| 13 鏡布置圖總耗時 | **0.8 秒** |
| 對比一次 H3 生成 | 數百秒 |

能攔下的問題：座位／朝向錯、背景多出物件、景別不符、道具位置、**不同鏡號共用同一機位**。

**布置圖保證的是空間關係，不是像素級構圖**：實測 A2 布置圖偏側背、成片偏正面 3/4，但座位與背景一致。不可宣稱鎖死構圖。

## 運鏡

- 相機運動**必須做成 keyframe**，不要靠算圖腳本逐格位移相機——否則 `.blend` 單獨交付時運鏡會消失。
- 插值用 **LINEAR**，才與逐格公式一致：

```python
from mathutils import Vector
base = cam.location.copy()
direction = cam.rotation_euler.to_quaternion() @ Vector((0, 0, -1))  # 視線方向
cam.animation_data_create()
cam.location = base
cam.keyframe_insert("location", frame=1)
cam.location = base + direction * distance
cam.keyframe_insert("location", frame=N)
```

- 驗證方式：重算該鏡全部幀，與原腳本產出逐格比對。**已驗證等價**（124 格差異 0.0047%、首尾格 0 像素差、位置偏差 1.1e-6 m）。

## 可重用檔案

- **不要覆寫既有 `.blend`**；另存新檔（例 `eatery_v5_reusable.blend`），原檔保留為歷史。
- 只保留**一個場景**。多場景＋多套相機是已發生的混淆來源。
- 移除不用的場景後，清掉 `users == 0` 的孤兒資料（objects / meshes / actions / worlds / collections），迴圈執行到沒有為止。
- 存檔前還原**正常預設狀態**：預設相機、角色全部可見、1536×864、frame range 覆蓋最長的鏡。
- 相機契約另存 `camera_plan_v<N>.json`。

## Blender 5.x API 陷阱（實際踩到）

| 症狀 | 正確做法 |
|:---|:---|
| `Action` 沒有 `.fcurves` | 5.x 改用 slots／layers：`act.layers[0].strips[0].channelbag(act.slots[0]).fcurves` |
| `Action` 沒有 `.fake_user` | 欄位名是 `use_fake_user` |
| `bpy.ops.wm.open_mainfile()` 後 `bpy.context.window` 是 `None` | 開檔後不要直接存取 `bpy.context.window`；改用 `bpy.data.scenes`，或先做一次無害呼叫再取 |
| 不確定屬性／enum 名稱 | 先用 `bpy_api_lookup`、`describe_node_type` 查，不要猜 |
| 假設燈光設定 | Workbench 不吃場景燈光；場景沒有 Light 也可能是正常的 |

## 檢查節點 ID

不同工作流的 Save 節點 ID 不同（v5 是 `SaveVideo` 15／生圖 `SaveImage` 7；外部工作流是 33／9）。**收件要鎖該工作流自己的節點**，不要遍歷所有輸出，否則會把輸入影片／圖片當成成品。
