# Recreating a piece from a reference

`reference.png` stands in for a screenshot or an artist's export: a 168 x 66 px HUD capsule (the background of
a resource counter), drawn with plain Pillow by `make_reference.py` (no ninekit code involved). `capsule.yaml`
recreates it with ninekit from measurements alone. Treat the reference as a 3x asset: `W / D = 168 / 56 = 3`.

## 1. Measure

```sh
ninekit measure examples/recreate/reference.png --x 84 --ref-width 168 --design-width 56   # centre column
ninekit measure examples/recreate/reference.png --y 15 --to 84 --ref-width 168 --design-width 56
```

| band (centre column) | px | dp | colours | layer |
|---|---|---|---|---|
| rim, top | 0-3 | 1.00 | `#0e3c49` | `rim`, a capsule `r: h / 2` |
| face | 3-50 | 15.67 | `#68d7e3` → `#248fa9` | `face`, inset by the rim |
| highlight over the face | 7-24 | 2.33-8.00 | `#c2edf2` → `#5bbfd0` | `highlight`, alpha solved from the face under it: 0.62 → 0.09 |
| lip | 50-57 | 2.33 | `#165f72` → `#114e5f` | `lip`, shows under the face |
| rim, bottom | 57-60 | 1.00 | `#0e3b49` | (the rim) |
| shadow | 60-65 | 1.67 | `#0b1c24`, alpha 91 | `shadow`, `soft`, `overhang: [0, 0, 0, 2]` |

The row through the highlight (`--y 15`) shows it starting 14 px (4.67 dp) from the left edge, inside the end cap,
so the middle columns stay identical and the capsule stretches.

## 2. Build, verify, compare

```sh
ninekit build examples/recreate/capsule.yaml && ninekit verify examples/recreate/capsule.yaml
ninekit compare examples/recreate/capsule.yaml capsule examples/recreate/reference.png --ref-scale 3
```

| metric | value |
|---|---|
| mean abs difference | 1.23 / 255 |
| max abs difference | 16 / 255 |
| PSNR | 40.88 dB |
| pixels over 16/255 | 0.00 % |

What is left is anti-aliasing along the curved edges (Pillow's rounded rectangle against ninekit's signed
distances) and the highlight's fade, which ninekit draws as a straight two-stop ramp. `verify` passes at 1x,
2x and 3x; the capsule is rounded over its whole height, so its y axis is `fixed`.
