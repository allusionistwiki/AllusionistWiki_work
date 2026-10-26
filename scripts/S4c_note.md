"""S4c: 裁定グラフの非推移適用再射影。

裁定 alias 辺を「推移閉包 DSU」でなく成分単位・辺単位で適用し、
辺間に矛盾（同じ a の canonical が複数 / 両方向の別名宣言）があれば
全ノードを個別 entity に戻す（統合しない）。表記ゆれ（同 norm_key）は機械統合のまま。
Usage: python scripts/build_l2_entities.py <run_id> --nontransitive
"""
