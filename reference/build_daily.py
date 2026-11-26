src=open("build.py").read().split("doc=BaseDocTemplate")[0]
exec(src)

def hero(c,doc):
    c.saveState(); hh=52*mm; y0=H-hh
    c.setFillColor(DG); c.rect(0,y0,W,hh,fill=1,stroke=0)
    c.setFillColor(colors.HexColor("#14633C")); c.circle(W-20*mm,H-8*mm,48*mm,fill=1,stroke=0)
    lw=40*mm; lh=lw*LH/LW; c.setFillColor(colors.white); c.roundRect(M,y0+(hh-lh)/2-1*mm,lw,lh,3*mm,fill=1,stroke=0)
    c.drawImage("logo.png",M+1.5*mm,y0+(hh-lh)/2-1*mm+1.5*mm,width=lw-3*mm,height=lh-3*mm,preserveAspectRatio=True)
    x=M+lw+8*mm
    c.setFillColor(LIME); c.setFont("P-B",7.5); c.drawString(x,H-14*mm,"EDMS  |  DAILY REPORT")
    c.setFillColor(colors.white); c.setFont("P-B",21); c.drawString(x,H-24*mm,"Daily Sales & Stock")
    c.setFillColor(LIME); c.drawString(x,H-33*mm,"Report")
    c.setFillColor(colors.HexColor("#CFE7D8")); c.setFont("P",8); c.drawString(x,H-40*mm,"Ripoti ya Siku - Mauzo, Stock na Shughuli za Ofisi")
    cx=x
    for t in ["Date: Wednesday 25/11/2026","Offices: Mwanza + Dar es Salaam","Status: Live data"]:
        tw=pdfmetrics.stringWidth(t,"P-M",6.5)+6*mm
        c.setFillColor(colors.HexColor("#1D7A4C")); c.roundRect(cx,H-48.5*mm,tw,5.2*mm,2.6*mm,fill=1,stroke=0)
        c.setFillColor(colors.white); c.setFont("P-M",6.5); c.drawString(cx+3*mm,H-46.9*mm,t); cx+=tw+2*mm
    c.restoreState(); footer(c,doc)
def header(c,doc):
    c.saveState(); c.setFillColor(DG); c.rect(0,H-14*mm,W,14*mm,fill=1,stroke=0)
    lh=9.5*mm; lw=lh*LW/LH; c.setFillColor(colors.white); c.roundRect(M,H-12*mm,lw+2*mm,lh+.5*mm,1.5*mm,fill=1,stroke=0)
    c.drawImage("logo.png",M+1*mm,H-11.6*mm,width=lw,height=lh-.3*mm,preserveAspectRatio=True)
    c.setFillColor(colors.white); c.setFont("P-B",8.5); c.drawRightString(W-M,H-6.5*mm,"Daily Sales & Stock Report")
    c.setFillColor(colors.HexColor("#CFE7D8")); c.setFont("P",6.8); c.drawRightString(W-M,H-10.5*mm,"Wednesday 25/11/2026  |  Mwanza + Dar es Salaam")
    c.restoreState(); footer(c,doc)

doc=BaseDocTemplate("/mnt/user-data/outputs/Effective_Diet_Daily_Report_25-11-2026.pdf",pagesize=A4,leftMargin=M,rightMargin=M,topMargin=M,bottomMargin=M,
    title="Effective Diet - Daily Report 25/11/2026",author="Effective Diet EDMS")
f1=Frame(M,16*mm,CW,H-52*mm-16*mm-8*mm,id="f1",leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
f2=Frame(M,16*mm,CW,H-14*mm-16*mm-6*mm,id="f2",leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
doc.addPageTemplates([PageTemplate("first",[f1],onPage=hero),PageTemplate("rest",[f2],onPage=header)])
sp=lambda h=4: Spacer(1,h*mm)
hs=S("h",fontName="P-B",fontSize=9.5,textColor=DG)
st=[NextPageTemplate("rest")]

# ---- PAGE 1 ----
st.append(Section("Day at a Glance","Muhtasari wa siku - Wednesday 25/11/2026"))
st.append(KPIRow([
 ("Sales today","TZS 1,040,000","Mwanza 400,000 | Dar 640,000",G),
 ("vs yesterday","+144.7%","Yesterday about TZS 425,000",AM),
 ("Units sold","28","4 Full Package + 24 pekee",BL),
 ("Closing stock","432","Mwanza 199 | Dar 233",DG),
 ("Customers served","6","Mwanza 2 | Dar 4",colors.HexColor("#8B5CF6")),
 ("Loss today","0","No loss recorded",RD)]))
st.append(sp(5))
st.append(two(card("Sales by branch",img("branch_sales_d",HW-8*mm),HW,"TZS, 25/11/2026"),
              card("Today vs yesterday",img("vs_yesterday",HW-8*mm),HW,"TZS  |  24/11 branch split read from system chart")))
st.append(sp(4))
st.append(Paragraph("<b>Sales by product</b>",hs)); st.append(sp(1.5))
d=[["Product","Mwanza sold","Dar sold","Total units","Closing Mwanza","Closing Dar"],
   ["Effective Diet Full Package","4","0","4","0","0"],["Effective Diet Pekee","0","1","1","66","49"],
   ["Presha Masala Pekee","0","23","23","127","169"],["Wild Honey / Asali Pekee","0","0","0","6","15"],["Total","4","24","28","199","233"]]
st.append(tbl(d,[52*mm,24*mm,22*mm,24*mm,32*mm,26*mm],total=True))
st.append(sp(4))
st.append(two(card("Units sold today",img("units_today",HW-8*mm),HW,"By product and branch"),
  card("Today's highlights",[
   Paragraph("<b>Best branch:</b> Dar es Salaam, TZS 640,000 (61.5% of the day).",note),sp(1.5),
   Paragraph("<b>Best product:</b> Presha Masala Pekee, 23 units, all in Dar.",note),sp(1.5),
   Paragraph("<b>Mwanza:</b> 4 Full Package units gave TZS 400,000.",note),sp(1.5),
   Paragraph("<b>Losses:</b> none. <b>Transfers:</b> none waiting.",note)],HW,"Main points")))
st.append(PageBreak())

# ---- PAGE 2 ----
st.append(Section("Branch Movement & Customers","Mwanza and Dar es Salaam - stock, customers and calls for the day"))
def btable(rows,total_sold,total_close):
    d=[["Product","Sold","Balance","Loss"]]+rows+[["Total",str(total_sold),str(total_close),"0"]]
    return tbl(d,[HW-8*mm-14*mm-17*mm-11*mm,14*mm,17*mm,11*mm],total=True)
st.append(two(
 card("Mwanza - sales TZS 400,000",btable([["Effective Diet Full Package","4","0","0"],["Effective Diet Pekee","0","66","0"],["Presha Masala Pekee","0","127","0"],["Wild Honey / Asali Pekee","0","6","0"]],4,199),HW),
 card("Dar es Salaam - sales TZS 640,000",btable([["Effective Diet Full Package","0","0","0"],["Effective Diet Pekee","1","49","0"],["Presha Masala Pekee","23","169","0"],["Wild Honey / Asali Pekee","0","15","0"]],24,233),HW)))
st.append(sp(4))
st.append(card("Closing balance by branch",img("branch_balance_d",CW-8*mm),CW,"Units available at the end of the day"))
st.append(sp(4))
st.append(Paragraph("<b>Customer activity</b>",hs)); st.append(sp(1.5))
st.append(tbl([["Measure","Mwanza","Dar es Salaam","Total"],["Customers","2","4","6"],["Customer visits today","1","2","3"],["Visitors today","0","0","0"],
  ["Recorded calls","1","0","1"],["Follow-ups","1","0","1"],["Customer areas","Tabata Barakuda, Mapinga","Tabata, Makole, Udom","-"]],[46*mm,52*mm,48*mm,34*mm],total=False))
st.append(sp(4))
st.append(Paragraph("<b>Follow-up due today</b>",hs)); st.append(sp(1.5))
st.append(tbl([["Due","Branch","Customer","Call type","Next step","Assigned","Priority"],
  ["25/11/2026","Mwanza","james","Instruction call","Contact customer and record the answer","emma","Normal"]],[22*mm,20*mm,20*mm,28*mm,50*mm,20*mm,20*mm],right_from=9))
st.append(sp(4))
st.append(insight("<b>Attention for tomorrow</b><br/>1. <b>Full Package</b> has 0 balance in both branches: plan production or transfer.<br/>2. <b>Wild Honey / Asali Pekee</b> is low in Mwanza (6 units).<br/>3. <b>Follow-up</b> for customer james (Mwanza) is due today and still open.<br/>4. <b>Branch daily reports:</b> none submitted yet, so nothing is waiting for manager approval.",AM,"#FFFBEB"))
st.append(sp(3))
sig=Table([["","","",""],[Paragraph("Mwanza branch",small),Paragraph("Dar branch",small),Paragraph("Reviewed by (CEO)",small),Paragraph("Date",small)]],colWidths=[CW/4]*4,rowHeights=[10*mm,8*mm])
sig.setStyle(TableStyle([("LINEBELOW",(0,0),(-1,0),.8,DG),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),6*mm)]))
st.append(sig)
st.append(Paragraph("Source: EDMS, 25/11/2026. Yesterday (about TZS 425,000) = all-time 1,465,000 minus today 1,040,000.",small))
doc.build(st,canvasmaker=NumCanvas); print("built")
