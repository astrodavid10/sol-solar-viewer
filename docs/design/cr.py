import colorsys
def hx(h):
    h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))
def lum(rgb):
    def f(c):
        c/=255.0
        return c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    r,g,b=[f(x) for x in rgb]
    return 0.2126*r+0.7152*g+0.0722*b
def cr(a,b):
    la,lb=lum(hx(a)),lum(hx(b))
    hi,lo=max(la,lb),min(la,lb)
    return (hi+0.05)/(lo+0.05)
def over(fg_rgba, bg):
    r,g,b,a = fg_rgba
    br,bg_,bb = hx(bg)
    return '#%02x%02x%02x' % (round(r*a+br*(1-a)), round(g*a+bg_*(1-a)), round(b*a+bb*(1-a)))
def hsl(h):
    r,g,b=[x/255 for x in hx(h)]
    hh,l,s=colorsys.rgb_to_hls(r,g,b)
    return round(hh*360,1), round(s*100,1), round(l*100,1)
def fromhsl(h,s,l):
    r,g,b=colorsys.hls_to_rgb(h/360,l/100,s/100)
    return '#%02x%02x%02x'%(round(r*255),round(g*255),round(b*255))

print("== brand HSL ==")
for n,c in [('Spaceberry','#0e0024'),('Spacebubble','#202267'),('MidnightCherry','#64102d'),
            ('Cosmaroon','#821036'),('NovaWhite','#EAEBEF'),('LightSpeedWhite','#f5f4f0'),
            ('Starliner','#D9DDE2'),('SpaceshipGray','#949baf')]:
    print(f"  {n:16s} {c}  hsl{hsl(c)}")

print("\n== ember: Cosmaroon hue lifted ==")
h,s,l = hsl('#821036')
for L in (55,58,62,66,70):
    c=fromhsl(h, 88, L)
    print(f"  L={L}  {c}  vs #0E0526 = {cr(c,'#0E0526'):.2f}:1   vs #FFFFFF = {cr(c,'#FFFFFF'):.2f}:1")

print("\n== violet: Spacebubble hue lifted ==")
h2,s2,l2 = hsl('#202267')
for L in (62,68,74):
    c=fromhsl(h2, 62, L)
    print(f"  L={L}  {c}  vs #0E0526 = {cr(c,'#0E0526'):.2f}:1")

print("\n== surface composites over pure black ==")
for rgba in [(16,6,42,0.90),(16,6,42,0.82),(9,2,24,0.86),(32,34,103,0.32)]:
    print("  rgba%s -> %s" % (rgba, over(rgba,'#000000')))

print("\n=== PROPOSED PALETTE CONTRAST TABLE ===")
PANEL='#0E0526'          # --sol-surface over black sky
PANEL_ON_SUN='#281F3F'   # same surface over a white disk
CHIP='#080215'           # --sol-label-bg over black
CHIP_ON_SUN='#241E33'    # over white
pairs=[
 ('Light Speed White #F5F4F0','#f5f4f0'),
 ('Starliner #D9DDE2','#D9DDE2'),
 ('Spaceship Gray #949BAF','#949baf'),
 ('Dim lifted #A6AEC4','#A6AEC4'),
 ('Quiet #7E86A0','#7E86A0'),
 ('Gold #FFC850','#FFC850'),
 ('Blue #5FB8FF','#5FB8FF'),
 ('Ember #F34982','#F34982'),
 ('Violet #7B7EE0','#7B7EE0'),
]
for bgname,bg in [('panel over black',PANEL),('panel over WHITE disk',PANEL_ON_SUN),
                  ('chip over black',CHIP),('chip over WHITE disk',CHIP_ON_SUN),
                  ('pure black sky','#000000'),('WHITE disk (no plate)','#FFFFFF')]:
    print(f"\n  -- on {bgname} ({bg})")
    for n,c in pairs:
        r=cr(c,bg)
        flag='AAA' if r>=7 else ('AA' if r>=4.5 else ('AA-lg' if r>=3 else 'FAIL'))
        print(f"     {n:26s} {r:6.2f}:1  {flag}")
