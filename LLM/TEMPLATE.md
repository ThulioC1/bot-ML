# Template `img/template.png` — medidas e uso

> Descoberto em 2026-10-14, pedido do usuário: *"verifica a pasta img. nela tem
> o templat que devemos usar. o preço deve ficar dentro do quadrado"*.
> **Status: IMPLEMENTADO** (opção C escolhida pelo usuário).

---

## 0. Implementado — opção C

O usuário escolheu a **opção C** e pediu explicitamente:
**"C. E não poe o titulo na arte. Ela ja esta na descrição"**.

Card final **1080×1350** (4:5, formato nativo do feed do Instagram):

```
+--------------------------------+   0
|                                |
|                                |
|      FOTO DO PRODUTO            |   até ~1050
|                                |
|                                |
+--------------------------------+  1121
| [yeti]  [-51%]  [ DE R$ 96,00 ]|  banner 1080x229
|           [ POR R$ 46,90 ]      |  (img/template.png)
+--------------------------------+  1350
```

### O que mudou no `bot.py`

**Constantes novas (bloco do `TEMPLATE_FILE`):**
```python
TEMPLATE_FILE = BASE_DIR / "img" / "template.png"   # era "template.png"  ← BUG A
TEMPLATE_W, TEMPLATE_H = 1024, 217
TEMPLATE_BOX = (576, 28, 951, 183)   # quadro de vidro, medido
TEMPLATE_BOX_PAD = 10
ART_W, ART_H = 1080, 1350            # 4:5 do Instagram
_TPL_SCALE = ART_W / TEMPLATE_W      # 1.0547
```

**Funções novas:**
| Função | O que faz |
|---|---|
| `_fit_font(draw, text, max_w, max_h, start, bold, minimum)` | maior fonte em que o texto cabe na caixa |
| `_draw_price_in_box(draw, box, preco, preco_original)` | escreve o preço **dentro** do quadro de vidro |
| `_draw_discount_badge(draw, box, desconto_pct)` | selo `-N%` no gelo à esquerda do quadro |

**`gerar_arte()` foi reescrita:**
- ❌ título **removido da arte** (continua na caption, L1485)
- ❌ barra "VAGANTE PROMOÇÕES" **removida** (o banner já tem o yeti de marca)
- ❌ pílula de preço branca **removida** (agora usa o quadro do template)
- ✅ banner colado embaixo, sem distorção (1080×229, mantém o ratio)
- ✅ preço dentro do quadro, em 2 linhas quando há desconto
- ✅ fonte do preço **auto-ajustada** — `R$ 1.299,00` cabe reduzindo a fonte
- ✅ fallback sem template preservado (cartão escuro)

### Bug extra corrigido no caminho

`ImageDraw` **sobrescreve** o pixel, não faz alpha-blend. O placeholder
antigo (`draw.rounded_rectangle(fill=(255,255,255,22))`) escrevia RGBA com
alpha 22; ao converter para JPEG o alpha era descartado e o retângulo saía
**branco sólido**. Corrigido desenhando num overlay separado +
`alpha_composite`.

O emoji 🛍️ também foi removido do placeholder: `load_font` cai em
`load_default()` (fonte bitmap) quando não acha TTF, e o emoji virava um
**bloco branco**. Agora mostra o texto "sem imagem".

### Testado

| Caso | Resultado |
|---|---|
| `46,90` de `96,00` (-51%) | ✅ |
| só `46,90` | ✅ |
| `1.299,00` de `2.499,00` (-48%) | ✅ fonte reduzida sozinha |
| `9,90` | ✅ |
| sem preço | ✅ "Confira na bio" |
| sem foto | ✅ placeholder translúcido |
| sem template | ✅ fallback escuro |

Todos geram **1080×1350**.

---

## 1. O arquivo

```
img/template.png   PNG, 1024 x 217 px, 95 KB
```

- Faixa panorâmica, ratio **4.72:1** — **não é quadrada**.
- Layout: **monstro/gelado à esquerda** (x 0–300) · **vazio no meio**
  (x 300–576) · **quadrado de vidro à direita** (x 576–951) ← preço.

## 2. Medidas do quadrado do preço

Detectadas por análise de brilho (borda de gelo), **no tamanho original 1024×217**:

| | x | y | largura | altura |
|---|---|---|---|---|
| Borda externa do quadro | 576 → 951 | 28 → 183 | 375 | 155 |
| **Área útil interna** (margem 10px) | 586 → 941 | 38 → 173 | **355** | **135** |
| Centro | **763** | **105** | | |

**Escalado para 1080px de largura** (fator `1080/1024 = 1.0547`):

| | x | y | largura | altura |
|---|---|---|---|---|
| Borda externa | **608 → 1003** | **30 → 193** | 395 | 163 |
| **Área útil interna** | 618 → 993 | 40 → 183 | **374** | **142** |
| **Centro** | **805** | **111** | | |

No card 1080×1350 com o banner embaixo (`banner_top = 1121`), o quadro fica em
**x 608→1003, y 1151→1314**.

---

## 3. 🔴 Bugs que foram encontrados (e corrigidos)

### Bug A — caminho errado (o template NUNCA era usado)

```python
TEMPLATE_FILE = BASE_DIR / "template.png"      # linha 102
```

O arquivo está em **`img/template.png`**. Então `TEMPLATE_FILE.exists()`
retornava **False** e o código caía silenciosamente no gradiente
(`custom_bg = usar_template and TEMPLATE_FILE.exists()` → `False`).

**Ninguém nunca percebeu porque não há erro — só um fallback silencioso.**

**Corrigido:** `TEMPLATE_FILE = BASE_DIR / "img" / "template.png"`

### Bug B — geometria quadrada vs template panorâmico

`gerar_arte` era escrito para um card **1080×1080**:

```python
canvas = Image.open(TEMPLATE_FILE).convert("RGBA").resize((size, size), ...)  # L567
```

1024×217 esticado para 1080×1080 = **distorção de ~5x na vertical**.

E **todos** os elementos usavam coordenadas de card quadrado:

| Elemento | Linha (antes) | Coordenada |
|---|---|---|
| Título do produto | 595 | y ≈ 155, centro x 540 |
| Badge de desconto | 631 | (600, 250) |
| Foto do produto | 611 | caixa (300, 240, 780, 720) |
| Pílula do preço | 635–653 | y = 790, centro x 540 |
| Barra "VAGANTE PROMOÇÕES" | 656 | y 1022–1080 |

→ **O preço era desenhado em `y=790`, fora da imagem de 217px.**

**Corrigido:** layout C, 1080×1350, com as constantes medidas do template.

---

## 4. Qual fonte cabe dentro do quadrado

Medido com `C:\Windows\Fonts\ariblk.ttf` (mesma fonte do `FONT_BOLD`),
área útil de **374 × 142 px**:

| Texto | Tamanho máx. | Ocupa |
|---|---|---|
| `R$ 46,90` | **78 px** | 373 × 77 |
| `POR R$ 46,90` | **50 px** | 372 × 50 |
| `R$ 1.299,00` | **56 px** | 360 × 56 |
| `DE R$ 96,00` | **56 px** | 370 × 56 |
| `-51%` | 140 px | 373 × 107 |

**Limite prático:** valores com 5+ dígitos (`R$ 1.299,00`) não cabem grandes.
Por isso o layout é de **2 linhas**, e `_fit_font` reduz a fonte
automaticamente quando o texto não cabe:

```python
de_font  = _fit_font(..., inner_h * 0.34, start=46, bold=False)   # "DE R$ 96,00"
por_font = _fit_font(..., inner_h * 0.60, start=62)               # "POR R$ 46,90"
gap      = 10 * _TPL_SCALE
```

O selo de desconto ficou **fora** do quadro, no gelo vazio à esquerda
(x termina 24px antes do quadro), para não colidir com o "DE R$".

---

## 5. Se o template mudar

Se `img/template.png` for substituído por outro com quadro em outra posição,
**atualize** `TEMPLATE_W`, `TEMPLATE_H` e `TEMPLATE_BOX` no topo do `bot.py`
e meça de novo (o método é análise de brilho da borda clara, igual foi feito
aqui). Todo o resto se ajusta sozinho via `_TPL_SCALE`.