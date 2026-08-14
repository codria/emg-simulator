# emg-simulator プロジェクトメモ

筋電ロボットアーム展示（オープンキャンパス）。EMG 2ch → 極座標 `(r, θ)` でロボット
アームを操作する到達ゲーム。**全面 Python 実装**。設計判断は
`docs/emg_robotarm_exhibit_design.md`（これが仕様の SSoT）。

## 環境・資材

- **conda env**: `env_emg-simulator`（Python 3.13）。依存は `requirements.txt`
  （現段階は numpy/scipy/pytest のみ、描画・取得系はコメントアウトで後回し）
- **GitHub**: `https://codria@github.com/codria/emg-simulator.git`（username 埋め込みで
  GCM prompt 回避、user global CLAUDE.md 参照）
- **C++ 参照資産**: `D:\github\KinectArmSimulator\KinectArmSimulator`
  - 元は Kinect で腕骨格を取得しロボットアームを駆動していた成熟プロジェクト
  - 本プロジェクトは §2.5 の方針で **IK 数式・アームモデル・湾曲アーム形状のみ回収**
  - 成果物に C++ は含めない

## 実装状況（layers は設計 §8）

| layer | 状態 |
|---|---|
| kinematics（アームモデル + IK） | **完了・C++ と数値検証済み** |
| acquisition / signal_processing / transform / rendering / game | 未着手 |

## kinematics 移植の要点（`emg_sim/kinematics/arm.py`）

C++ 元: `KinectArmSimulator/src/window3/arm.{h,cpp}`（さらに元は `arm_threejs_v21.html`）。

- **6自由度・減衰最小二乗（DLS/Levenberg-Marquardt）ヤコビアン IK** + 副次タスク
  （肘上げ・J1 ヨーで Z 軸特異点回避・J4/J5 姿勢誘導）を移植。
- **GLM 規約の numpy 対応づけ**（ここを間違えると全部ずれる）:
  - GLM は列優先ストレージだが数学は `v' = M·v`（列ベクトル）。numpy は標準行列 `M @ v`。
  - フレーム連結は後乗算: `T = T @ Trans(offset) @ Rot(q, axis)`。
  - `glm Ts[k][3]`（4列目=並進）→ `Ts[k][:3, 3]`。`glm::mat3(Ts[k])`（回転）→ `Ts[k][:3, :3]`。
  - `glm R * v` → `R @ v`。回転行列は GLM `rotate` 一致の Rodrigues。
  - `JJ^T` は対称なので det/inverse は列優先/行優先の別を気にせず一致する。
- C++ は float32、本移植は float64（展示用途で条件数的に有利）。差は丸めレベル。
- `ArmDimensions` は arm.h の定数を移植（**t7_len=0.05, t10_len=0.05** に注意、
  他 tube は 0.060。転記ミスしやすい）。q=0 で先端は真上 z≈0.777 m。

## C++↔numpy 検証（§2.5 の「関節角突き合わせ」）

`tools/cpp_ref/dump_ref.cpp` を arm.cpp 単体 + GLM でビルド→固定 q の FK・固定 target の
IK を `ref_cases.json` に出力（コミット済み）。`tools/verify_ik_vs_cpp.py` と
`tests/test_arm_ik.py` が同一入力で numpy を回して突き合わせる。
**実測一致: FK ~1e-7, IK 関節角 ~1e-7、収束フラグも全一致**。

再生成: `bash tools/cpp_ref/build_and_dump.sh`（g++ mingw64 + KAS repo が要る。
ref_cases.json はコミット済みなので pytest は g++ 無しで回る）。

### ⚠️ g++ ビルドの罠（既知）

arm.h の `solveIK(..., const IKOptions& opts = {})` は **g++ が拒否**する
（`IKOptions` が `Manipulator` のネスト型で、未完成の外側クラス内でデフォルト
メンバ初期化子を使う aggregate `{}` を構築 →「default member initializer required
before the end of its enclosing class」。MSVC/Clang は許容）。
build スクリプトは **KAS ツリーを触らず**、build/ にコピーした arm.h へ
`sed` で「デフォルト引数 `= {}` を除去」する 1 行 patch を当てる（この既定値は
arm.cpp でも dumper でも未使用なので挙動不変）。

## 未決定（設計 §9、実装に直結する大物）

- **位置制御 or 速度制御**（§3.5）。速度制御だとバー上目標マーカーが原理的に引けない
- **バー上目標マーカーの有無**（§5.5、出すなら位置制御前提）
- `r_min/r_max/θ` 範囲・RMS 窓長・到達判定閾値は実機到着後に実測で詰める

## 着手順（設計 §10）

取得系(1-4)と描画系(5-7)は独立。描画系は実機前でも着手可。IK 移植(5)は完了済み。
```
