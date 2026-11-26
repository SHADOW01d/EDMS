from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
                                Image, KeepTogether, PageBreak, Flowable, NextPageTemplate)
from PIL import Image as PILImage

FD="/usr/share/fonts/truetype/google-fonts/"
for n,f in [("P","Regular"),("P-M","Medium"),("P-B","Bold"),("P-I","Italic")]:
    pdfmetrics.registerFont(TTFont(n,FD+f"Poppins-{f}.ttf"))
pdfmetrics.registerFontFamily("P",normal="P",bold="P-B",italic="P-I",boldItalic="P-B")

DG=colors.HexColor("#0F4A2E"); G=colors.HexColor("#16A34A"); AM=colors.HexColor("#F59E0B"); BL=colors.HexColor("#3B82F6")
RD=colors.HexColor("#DC2626"); LG=colors.HexColor("#F1F7F3"); LINE=colors.HexColor("#DCE7DF"); TXT=colors.HexColor("#1F2937"); MUT=colors.HexColor("#6B7280")
LIME=colors.HexColor("#C6F135")
W,H=A4; M=15*mm; CW=W-2*M

def S(name,**kw):
    base=dict(fontName="P",fontSize=8.5,leading=12.5,textColor=TXT); base.update(kw); return ParagraphStyle(name,**base)
body=S("body"); small=S("small",fontSize=7.5,leading=11,textColor=MUT)
cell=S("cell",fontSize=8,leading=10.5); cellb=S("cellb",fontName="P-B",fontSize=8,leading=10.5)
cellr=S("cellr",fontSize=8,leading=10.5,alignment=TA_RIGHT)
th=S("th",fontName="P-B",fontSize=7,leading=9,textColor=colors.white)
thr=S("thr",fontName="P-B",fontSize=7,leading=9,textColor=colors.white,alignment=TA_RIGHT)
note=S("note",fontSize=8,leading=12)

lg=PILImage.open("logo.png"); LW,LH=lg.size

# ---------- flowables ----------
class Section(Flowable):
    def __init__(s,title,sub=""): super().__init__(); s.t=title; s.sub=sub; s.width=CW; s.height=11*mm
    def wrap(s,aw,ah): return CW,s.height
    def draw(s):
        c=s.canv; c.setFillColor(G); c.roundRect(0,1.5*mm,1.6*mm,7*mm,.8*mm,fill=1,stroke=0)
        c.setFillColor(DG); c.setFont("P-B",12); c.drawString(4.5*mm,5.6*mm,s.t)
        if s.sub: c.setFillColor(MUT); c.setFont("P",7.5); c.drawString(4.5*mm,1.6*mm,s.sub)

class KPIRow(Flowable):
    def __init__(s,items,cols=3,h=21*mm,gap=3*mm):
        super().__init__(); s.items=items; s.cols=cols; s.h=h; s.gap=gap
        s.rows=-(-len(items)//cols)
    def wrap(s,aw,ah): return CW,s.rows*s.h+(s.rows-1)*s.gap
    def draw(s):
        c=s.canv; cw=(CW-(s.cols-1)*s.gap)/s.cols
        for i,(label,val,sub,col) in enumerate(s.items):
            r,k=divmod(i,s.cols); x=k*(cw+s.gap); y=(s.rows-1-r)*(s.h+s.gap)
            c.setFillColor(colors.white); c.setStrokeColor(LINE); c.setLineWidth(.8); c.roundRect(x,y,cw,s.h,2.5*mm,fill=1,stroke=1)
            c.setFillColor(col); c.roundRect(x,y+3*mm,1.3*mm,s.h-6*mm,.6*mm,fill=1,stroke=0)
            c.setFillColor(MUT); c.setFont("P-M",6.8); c.drawString(x+5*mm,y+s.h-6.2*mm,label.upper())
            c.setFillColor(DG); c.setFont("P-B",15 if len(val)<12 else 12.5); c.drawString(x+5*mm,y+s.h-13.5*mm,val)
            c.setFillColor(MUT); c.setFont("P",6.8); c.drawString(x+5*mm,y+2.8*mm,sub)

def img(name,w):
    p=f"charts/{name}.png"; iw,ih=PILImage.open(p).size; return Image(p,width=w,height=w*ih/iw)

def card(title,flow,w,sub=None):
    inner=[Paragraph(f"<b>{title}</b>",S("ct",fontName="P-B",fontSize=9,textColor=DG,leading=12))]
    if sub: inner.append(Paragraph(sub,small))
    inner+= flow if isinstance(flow,list) else [flow]
    t=Table([[inner]],colWidths=[w])
    t.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.8,LINE),("BACKGROUND",(0,0),(-1,-1),colors.white),
        ("LEFTPADDING",(0,0),(-1,-1),4*mm),("RIGHTPADDING",(0,0),(-1,-1),4*mm),("TOPPADDING",(0,0),(-1,-1),3*mm),("BOTTOMPADDING",(0,0),(-1,-1),3*mm),
        ("ROUNDEDCORNERS",[6,6,6,6])]))
    return t

def two(a,b,gap=4*mm):
    w=(CW-gap)/2; t=Table([[a,b]],colWidths=[w,w+gap]);
    t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(0,0),gap),("RIGHTPADDING",(1,0),(1,0),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    return t
HW=(CW-4*mm)/2

def tbl(data,widths,right_from=1,total=False,zebra=True,align_all_right=False,hl_cells=()):
    rows=[]
    for i,r in enumerate(data):
        row=[]
        for j,v in enumerate(r):
            if i==0: row.append(Paragraph(str(v),thr if j>=right_from else th))
            else:
                st=cellr if j>=right_from else cell
                if (total and i==len(data)-1) or j==0 and False: st=ParagraphStyle("x",parent=st,fontName="P-B")
                row.append(Paragraph(str(v),st))
        rows.append(row)
    t=Table(rows,colWidths=widths,repeatRows=1)
    st=[("BACKGROUND",(0,0),(-1,0),DG),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("LINEBELOW",(0,1),(-1,-1),.5,LINE),("BOX",(0,0),(-1,-1),.6,LINE)]
    if zebra:
        for i in range(2,len(data),2): st.append(("BACKGROUND",(0,i),(-1,i),LG))
    if total: st+= [("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#E3F0E7")),("LINEABOVE",(0,-1),(-1,-1),1,DG)]
    t.setStyle(TableStyle(st)); return t

def insight(text,color=G,bg="#EEF8F1"):
    p=Paragraph(text,note)
    t=Table([[p]],colWidths=[CW]); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor(bg)),("LINEBEFORE",(0,0),(0,-1),2.2,color),
        ("LEFTPADDING",(0,0),(-1,-1),4*mm),("RIGHTPADDING",(0,0),(-1,-1),4*mm),("TOPPADDING",(0,0),(-1,-1),3*mm),("BOTTOMPADDING",(0,0),(-1,-1),3*mm)])); return t

# ---------- page decorations ----------
def hero(c,doc):
    c.saveState()
    hh=52*mm; y0=H-hh
    c.setFillColor(DG); c.rect(0,y0,W,hh,fill=1,stroke=0)
    c.setFillColor(colors.HexColor("#14633C")); c.circle(W-20*mm,H-8*mm,48*mm,fill=1,stroke=0)
    c.setFillColor(colors.HexColor("#0F4A2E")); c.circle(W-4*mm,y0-4*mm,30*mm,fill=1,stroke=0)
    c.setFillColor(DG); c.rect(0,y0-10*mm,W,10*mm,fill=0,stroke=0)
    # logo card
    lw=40*mm; lh=lw*LH/LW; c.setFillColor(colors.white); c.roundRect(M,y0+(hh-lh)/2-1*mm,lw,lh,3*mm,fill=1,stroke=0)
    c.drawImage("logo.png",M+1.5*mm,y0+(hh-lh)/2-1*mm+1.5*mm,width=lw-3*mm,height=lh-3*mm,mask=None,preserveAspectRatio=True)
    x=M+lw+8*mm
    c.setFillColor(LIME); c.setFont("P-B",7.5); c.drawString(x,H-14*mm,"EDMS  |  MANAGEMENT REPORT")
    c.setFillColor(colors.white); c.setFont("P-B",21); c.drawString(x,H-24*mm,"Sales, Stock & Operations")
    c.setFont("P-B",21); c.setFillColor(LIME); c.drawString(x,H-33*mm,"Report")
    c.setFillColor(colors.HexColor("#CFE7D8")); c.setFont("P",8); c.drawString(x,H-40*mm,"Ripoti ya Mauzo, Maghala na Shughuli za Ofisi")
    # chips
    cx=x
    for t in ["Period: 26/10/2026 - 25/11/2026","Offices: Mwanza + Dar es Salaam","Generated: 25/11/2026"]:
        tw=pdfmetrics.stringWidth(t,"P-M",6.5)+6*mm
        c.setFillColor(colors.HexColor("#1D7A4C")); c.roundRect(cx,H-48.5*mm,tw,5.2*mm,2.6*mm,fill=1,stroke=0)
        c.setFillColor(colors.white); c.setFont("P-M",6.5); c.drawString(cx+3*mm,H-46.9*mm,t); cx+=tw+2*mm
    c.restoreState(); footer(c,doc)

def header(c,doc):
    c.saveState()
    c.setFillColor(DG); c.rect(0,H-14*mm,W,14*mm,fill=1,stroke=0)
    lh=9.5*mm; lw=lh*LW/LH; c.setFillColor(colors.white); c.roundRect(M,H-12*mm,lw+2*mm,lh+.5*mm,1.5*mm,fill=1,stroke=0)
    c.drawImage("logo.png",M+1*mm,H-11.6*mm,width=lw,height=lh-.3*mm,preserveAspectRatio=True)
    c.setFillColor(colors.white); c.setFont("P-B",8.5); c.drawRightString(W-M,H-6.5*mm,"Sales, Stock & Operations Report")
    c.setFillColor(colors.HexColor("#CFE7D8")); c.setFont("P",6.8); c.drawRightString(W-M,H-10.5*mm,"26/10/2026 - 25/11/2026  |  Mwanza + Dar es Salaam")
    c.restoreState(); footer(c,doc)

def footer(c,doc):
    c.saveState(); c.setStrokeColor(LINE); c.setLineWidth(.6); c.line(M,12*mm,W-M,12*mm)
    c.setFillColor(MUT); c.setFont("P",6.8); c.drawString(M,8*mm,"Effective Diet  |  Stay Healthy, Be Productive  |  Confidential - for management use")
    c.restoreState()

class NumCanvas(rl_canvas.Canvas):
    def __init__(s,*a,**k): super().__init__(*a,**k); s._pages=[]
    def showPage(s): s._pages.append(dict(s.__dict__)); s._startPage()
    def save(s):
        n=len(s._pages)
        for st in s._pages:
            s.__dict__.update(st); s.setFillColor(MUT); s.setFont("P-M",6.8); s.drawRightString(W-M,8*mm,f"Page {s._pageNumber} of {n}"); super().showPage()
        super().save()

doc=BaseDocTemplate("/mnt/user-data/outputs/Effective_Diet_Management_Report.pdf",pagesize=A4,leftMargin=M,rightMargin=M,topMargin=M,bottomMargin=M,
    title="Effective Diet - Sales, Stock & Operations Report",author="Effective Diet EDMS")
f1=Frame(M,16*mm,CW,H-52*mm-16*mm-8*mm,id="f1",leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
f2=Frame(M,16*mm,CW,H-14*mm-16*mm-6*mm,id="f2",leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
doc.addPageTemplates([PageTemplate("first",[f1],onPage=hero),PageTemplate("rest",[f2],onPage=header)])

sp=lambda h=4: Spacer(1,h*mm)
st=[NextPageTemplate("rest")]

# ===== PAGE 1: Executive summary =====
st.append(Section("Executive Summary","Muhtasari wa Mkurugenzi - the whole business at a glance"))
st.append(KPIRow([
 ("Total sales (to date)","TZS 1,465,000","Live system total",G),
 ("Sales today","TZS 1,040,000","25/11/2026",AM),
 ("Units produced","580","All-time production",BL),
 ("Units in stock","527","Store 95  |  Mwanza 199  |  Dar 233",DG),
 ("Active customers","6","Mwanza 2  |  Dar 4",colors.HexColor("#8B5CF6")),
 ("Losses","0","No loss recorded",RD)]))
st.append(sp(5))
st.append(card("Daily sales trend by branch",img("trend",CW-8*mm),CW,"Week 23/11 - 29/11/2026  |  TZS per day  |  24/11 split read from the system chart"))
st.append(sp(4))
hl=[Paragraph("<b>Dar es Salaam leads today.</b> It made TZS 640,000 (61.5% of today's sales) against Mwanza's TZS 400,000 (38.5%).",note),sp(1.5),
    Paragraph("<b>Presha Masala Pekee is the top mover.</b> 23 units sold in Dar today and 40 over the period. It is also the biggest stock line (306 units).",note),sp(1.5),
    Paragraph("<b>Full Package is out of stock.</b> Closing balance is 0 in both branches after 4 units sold in Mwanza.",note),sp(1.5),
    Paragraph("<b>Zero losses</b> recorded in both branches and no transfers waiting.",note),sp(1.5),
    Paragraph("<b>Customer care has started:</b> 1 instruction call recorded and 1 follow-up due today.",note)]
st.append(two(card("Stock distribution",img("donut",HW-8*mm),HW,"Where the 527 units are today"),card("Key highlights",hl,HW,"What the manager should know")))
st.append(PageBreak())

# ===== PAGE 2: Sales =====
st.append(Section("Sales Performance","Utendaji wa Mauzo - by branch and by product"))
st.append(KPIRow([("Sales today","TZS 1,040,000","Mwanza + Dar",G),("Units sold today","28","4 Full Package + 24 pekee",AM),("Customers","6","Active customer records",BL)],cols=3,h=19*mm))
st.append(sp(4))
d=[["Branch","Sales today (TZS)","Share","Units sold","Customers","Loss"],
   ["Mwanza","400,000","38.5%","4","2","0"],["Dar es Salaam","640,000","61.5%","24","4","0"],["Total","1,040,000","100%","28","6","0"]]
st.append(tbl(d,[44*mm,38*mm,24*mm,26*mm,26*mm,22*mm],total=True))
st.append(sp(4))
d=[["Product","Mwanza sold","Dar sold","Total sold today"],
   ["Effective Diet Full Package","4","0","4"],["Effective Diet Pekee","0","1","1"],["Presha Masala Pekee","0","23","23"],["Wild Honey / Asali Pekee","0","0","0"],["Total","4","24","28"]]
st.append(tbl(d,[70*mm,36*mm,36*mm,38*mm],total=True))
st.append(sp(5))
st.append(two(card("Sales by branch today",img("branch_sales",HW-8*mm),HW,"TZS, 25/11/2026"),
              card("Units sold by product",img("units_sold",HW-8*mm),HW,"Period 26/10 - 25/11/2026, as shown in the system")))
st.append(sp(4))
st.append(insight("<b>Reading the numbers:</b> Mwanza's TZS 400,000 came from only 4 Full Package units, so each unit is a high-value sale (implied TZS 100,000 each). Dar's TZS 640,000 came from 24 smaller units, mostly Presha Masala Pekee. Adding a <b>unit price</b> column to the product records will let this report show revenue per product automatically."))
st.append(PageBreak())

# ===== PAGE 3: Stock =====
st.append(Section("Stock & Inventory","Maghala na Vifungashio - production against current stock in all locations"))
st.append(KPIRow([("Produced (all time)","580","3 pekee products",BL),("In stock now","527","90.9% of production",G),("Store","95","Central store",DG),("Branches","432","Mwanza 199 + Dar 233",AM)],cols=4,h=19*mm,gap=2.5*mm))
st.append(sp(4))
d=[["Product","Produced","Store","Mwanza","Dar","Current stock","In stock %"],
   ["Effective Diet Pekee","200","80","66","49","195","97.5%"],["Presha Masala Pekee","350","10","127","169","306","87.4%"],
   ["Wild Honey / Asali Pekee","30","5","6","15","26","86.7%"],["Total","580","95","199","233","527","90.9%"]]
st.append(tbl(d,[48*mm,22*mm,19*mm,22*mm,19*mm,29*mm,21*mm],total=True))
st.append(Paragraph("Effective Diet Full Package is sold in the branches (closing balance 0 in both) but is not part of the production and store table.",small))
st.append(sp(4))
st.append(two(card("Stock by product and location",img("stock_stacked",HW-8*mm),HW,"Units"),card("Produced vs current stock",img("prod_vs_stock",HW-8*mm),HW,"Units, all time")))
st.append(sp(4))
st.append(card("Closing balance by branch",img("branch_balance",CW-8*mm),CW,"Units available at the end of 25/11/2026"))
st.append(sp(4))
st.append(insight("<b>Stock alerts</b><br/><b>Out of stock:</b> Effective Diet Full Package has 0 balance in Mwanza and Dar. Plan production or a transfer.<br/><b>Low central store:</b> Presha Masala has only 10 units and Wild Honey 5 in store. At Dar's pace (23 Presha a day) its 169 units last about 7 days.<br/><b>Watch:</b> Mwanza has only 6 Wild Honey / Asali Pekee left.",AM,"#FFFBEB"))
st.append(PageBreak())

# ===== PAGE 4: Branches =====
st.append(Section("Branch Detail","Matawi - allocation, sales, closing balance and customer activity"))
def branch(name,color,stock,sales,rows,cust,areas):
    kp=KPIRow([("Stock",str(stock),"Units in branch",BL),("Sales today",f"TZS {sales}","25/11/2026",color),("Pending transfers","0","Nothing waiting",DG),("Loss today","0","25/11/2026",RD)],cols=4,h=19*mm,gap=2.5*mm)
    d=[["Product","Sold","Balance","Loss"]]+rows+[["Total",str(sum(int(r[1]) for r in rows)),str(stock),"0"]]
    left=tbl(d,[HW-8*mm-14*mm-17*mm-11*mm,14*mm,17*mm,11*mm],total=True)
    c=[["Customer activity","Count"]]+cust
    right=tbl(c,[HW-8*mm-16*mm,16*mm],right_from=1)
    return [Paragraph(f"<b>{name}</b>",S("bh",fontName="P-B",fontSize=11,textColor=DG)),sp(1.5),kp,sp(3),
            two(card("Stock by product",left,HW),card("Customers",[right,sp(2),Paragraph(f"<b>Customer areas:</b> {areas}",note)],HW)),sp(5)]
st+=branch("Mwanza Branch",G,199,"400,000",
  [["Effective Diet Full Package","4","0","0"],["Effective Diet Pekee","0","66","0"],["Presha Masala Pekee","0","127","0"],["Wild Honey / Asali Pekee","0","6","0"]],
  [["Customers","2"],["Customer visits today","1"],["Visitors today","0"],["Recorded calls","1"],["Follow-ups","1"]],"Tabata Barakuda, Mapinga")
st+=branch("Dar es Salaam Branch",AM,233,"640,000",
  [["Effective Diet Full Package","0","0","0"],["Effective Diet Pekee","1","49","0"],["Presha Masala Pekee","23","169","0"],["Wild Honey / Asali Pekee","0","15","0"]],
  [["Customers","4"],["Customer visits today","2"],["Visitors today","0"],["Recorded calls","0"],["Follow-ups","0"]],"Tabata, Makole, Udom")
st.append(insight("<b>Comparison:</b> Dar holds more stock (233 vs 199) and sells far more units, but Mwanza earns more per unit. Dar serves 4 customers across 3 areas; Mwanza serves 2 customers across 2 areas."))
st.append(PageBreak())

# ===== PAGE 5: Customers & Calls =====
st.append(Section("Customers, Operations & Calls","Wateja, Shughuli za Ofisi na Simu - 26/10/2026 to 25/11/2026"))
st.append(KPIRow([("Customers","6","Total",BL),("New / returning","1 / 1","Wapya / Wamarudio",G),("Deliveries","14","Delivered",AM),("Parcels","3","Sent",DG)],cols=4,h=19*mm,gap=2.5*mm))
st.append(sp(4))
d=[["Date","Branch","Customers","Customer area"],
 ["25/11/2026","Mwanza","1","Tabata Barakuda"],["25/11/2026","Dar es Salaam","1","-"],["25/11/2026","Dar es Salaam","1","Udom"],
 ["24/11/2026","Dar es Salaam","1","Tabata"],["24/11/2026","Mwanza","1","Mapinga"],["24/11/2026","Dar es Salaam","1","Tabata"],
 ["24/11/2026","Dar es Salaam","1","Makole"],["24/11/2026","Mwanza","1","Mapinga"],["24/11/2026","Mwanza","1","Mapinga"]]
t=tbl(d,[34*mm,46*mm,30*mm,70*mm],right_from=2)
st.append(Paragraph("<b>Daily customer log</b>",S("h",fontName="P-B",fontSize=9.5,textColor=DG))); st.append(sp(1.5)); st.append(t)
st.append(sp(5))
calls=[Paragraph("<b>Call workflow</b>",S("ct",fontName="P-B",fontSize=9,textColor=DG)),sp(1),
 Paragraph("<b>Instruction:</b> explain product use or the agreed diet plan.",note),sp(1),
 Paragraph("<b>Compliance:</b> check adherence, progress and side effects.",note),sp(1),
 Paragraph("<b>Follow-up:</b> set due date, owner and next action until resolved.",note)]
st.append(two(card("Call activity by category",img("calls",HW-8*mm),HW,"Recorded calls, all branches"),card("Call KPIs",[sp(1)]+[
   Paragraph("<b>1</b> instruction call",note),sp(1),Paragraph("<b>0</b> compliance calls",note),sp(1),Paragraph("<b>0</b> follow-up calls",note),sp(1),Paragraph("<b>1</b> follow-up due today",note),sp(3)]+calls[2:],HW,"Live totals")))
st.append(sp(5))
st.append(Paragraph("<b>Follow-up queue</b>",S("h",fontName="P-B",fontSize=9.5,textColor=DG))); st.append(sp(1.5))
st.append(tbl([["Due","Branch","Customer","Call type","Next step","Assigned","Priority"],
  ["25/11/2026","Mwanza","james","Instruction call","Contact customer and record the answer","emma","Normal"]],[22*mm,20*mm,20*mm,28*mm,50*mm,20*mm,20*mm],right_from=9))
st.append(sp(4))
st.append(Paragraph("<b>Call history</b>",S("h",fontName="P-B",fontSize=9.5,textColor=DG))); st.append(sp(1.5))
st.append(tbl([["Date / time","Branch","Customer","Call type","Next call","Recorded by"],
  ["24/11/2026 11:36","Mwanza","james","Instruction call","25/11/2026","emma"]],[34*mm,22*mm,24*mm,38*mm,32*mm,30*mm],right_from=9))
st.append(PageBreak())

# ===== PAGE 6: Data notes & sign-off =====
st.append(Section("Data Quality Notes & Next Steps","Points found while reading the system screens - worth fixing so reports stay accurate"))
notes=[
 ("Store stock mismatch","The Dashboard card and donut show Store = <b>295</b>, but the product table adds up to <b>95</b> (80 + 10 + 5). 295 + 199 + 233 = 727 is more than the 580 ever produced, so 95 is used in this report. Please check how the Store card is calculated."),
 ("Sales report total","On Ripoti ya Mauzo the card says 'Jumla ya Mauzo (Leo)' and shows TZS 1,040,000 (today only) while the date range is a full month. The all-time total is TZS 1,465,000. A period report should total the whole selected period."),
 ("Empty product columns","In the sales table the per-product columns (Mauzo / Balance) are blank on every daily row, yet the totals row shows values. Daily rows should carry the product units and TZS for each row."),
 ("Follow-ups due today","The Calls page shows 1 in the 'due today' card but '2 due today' on the queue badge, with only 1 row listed."),
 ("Test-looking entries","The call record contains values such as 'fhfrtutyk' and 'aatsdghf', and the phone number reads 'Haikubainishwa' (not specified). Clean these before sharing reports with outsiders."),
 ("Missing prices","No unit prices are visible. Adding price per product lets the report show revenue per product, average price and profit margin."),
 ("Full Package tracking","Full Package appears in branch sales but not in the production/store table, so its stock cannot be reconciled."),
]
for i,(h,t) in enumerate(notes,1):
    row=Table([[Paragraph(f"<b>{i}</b>",S("n",fontName="P-B",fontSize=10,textColor=colors.white,alignment=TA_CENTER)),Paragraph(f"<b>{h}.</b> {t}",note)]],colWidths=[8*mm,CW-8*mm])
    row.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),G),("BACKGROUND",(1,0),(1,0),LG),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(1,0),(1,0),4*mm),
       ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
    st.append(row); st.append(sp(1.5))
st.append(sp(4))
st.append(Section("Approval","Idhinisho"))
sig=Table([["","",""],[Paragraph("Prepared by",small),Paragraph("Reviewed by (CEO / Manager)",small),Paragraph("Date",small)]],colWidths=[CW/3]*3,rowHeights=[16*mm,6*mm])
sig.setStyle(TableStyle([("LINEBELOW",(0,0),(-1,0),.8,DG),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),8*mm)]))
st.append(sig)
st.append(sp(4))
st.append(Paragraph("Figures are taken from the EDMS screens of 25/11/2026. The 24/11 split by branch in the trend chart and the units-sold chart are read from the system's own charts.",small))

doc.build(st,canvasmaker=NumCanvas)
print("built")
