import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.ticker import FuncFormatter
import numpy as np

for f in ["Regular","Medium","Bold"]:
    fm.fontManager.addfont(f"/usr/share/fonts/truetype/google-fonts/Poppins-{f}.ttf")
plt.rcParams.update({"font.family":"Poppins","font.size":8,"axes.edgecolor":"#D6E2DA",
    "axes.labelcolor":"#4B5B52","xtick.color":"#4B5B52","ytick.color":"#4B5B52",
    "axes.spines.top":False,"axes.spines.right":False,"figure.dpi":100})

DG="#0F4A2E"; G="#16A34A"; A="#F59E0B"; B="#3B82F6"; R="#DC2626"; GRID="#E3ECE6"
def money(x,_=None): return f"{int(x):,}"
def save(fig,name):
    fig.savefig(f"charts/{name}.png",dpi=240,bbox_inches="tight",facecolor="white"); plt.close(fig)

# 1 Sales trend (read from system chart; 24/11 approximate split)
days=["Mon\n23/11","Tue\n24/11","Wed\n25/11","Thu\n26/11","Fri\n27/11","Sat\n28/11","Sun\n29/11"]
mw=[0,225000,400000,0,0,0,0]; dar=[0,200000,640000,0,0,0,0]
x=np.arange(7)
fig,ax=plt.subplots(figsize=(7.1,2.15))
xs=np.linspace(0,6,300)
from scipy.interpolate import PchipInterpolator
for vals,c,l in [(dar,A,"Dar es Salaam"),(mw,G,"Mwanza")]:
    y=PchipInterpolator(x,vals)(xs); ax.plot(xs,y,color=c,lw=2.2,label=l); ax.fill_between(xs,y,color=c,alpha=.12)
    ax.scatter(x,vals,s=22,color="white",edgecolor=c,zorder=5,lw=1.6)
ax.annotate("TZS 640,000",(2,640000),xytext=(2.35,665000),fontsize=7.5,color="#B45309",fontweight="bold")
ax.annotate("TZS 400,000",(2,400000),xytext=(2.35,330000),fontsize=7.5,color="#166534",fontweight="bold")
ax.set_xticks(x); ax.set_xticklabels(days); ax.set_ylim(0,760000)
ax.yaxis.set_major_formatter(FuncFormatter(money)); ax.grid(axis="y",color=GRID,lw=.8); ax.set_axisbelow(True)
ax.legend(frameon=False,loc="upper left",ncol=1); save(fig,"trend")

# 2 Donut stock distribution
fig,ax=plt.subplots(figsize=(3.5,1.9))
vals=[95,199,233]; cols=[DG,B,A]
ax.pie(vals,colors=cols,startangle=90,counterclock=False,wedgeprops=dict(width=.34,edgecolor="white",linewidth=2))
ax.text(0,.08,"527",ha="center",va="center",fontsize=15,fontweight="bold",color=DG)
ax.text(0,-.22,"units",ha="center",va="center",fontsize=7.5,color="#4B5B52")
ax.legend([f"Store  {95}  ({95/527:.0%})",f"Mwanza  {199}  ({199/527:.0%})",f"Dar  {233}  ({233/527:.0%})"],
    loc="center left",bbox_to_anchor=(1.02,.5),frameon=False,ncol=1,fontsize=7.5,handlelength=1,labelspacing=.4)
save(fig,"donut")

# 3 Sales by branch today
fig,ax=plt.subplots(figsize=(3.4,2.1))
b=ax.bar(["Mwanza","Dar es Salaam"],[400000,640000],color=[G,A],width=.55)
for r,v in zip(b,[400000,640000]): ax.text(r.get_x()+r.get_width()/2,v+15000,f"{v:,}",ha="center",fontsize=7.5,fontweight="bold",color="#1F2937")
ax.yaxis.set_major_formatter(FuncFormatter(money)); ax.set_ylim(0,760000); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True)
save(fig,"branch_sales")

# 4 Units sold by product (period, as shown in system chart)
fig,ax=plt.subplots(figsize=(3.4,2.1))
names=["Effective Diet\nPekee","Presha Masala\nPekee","Wild Honey /\nAsali Pekee"]; v=[1,40,0]
b=ax.bar(names,v,color=G,width=.5)
for r,val in zip(b,v): ax.text(r.get_x()+r.get_width()/2,val+1,str(val),ha="center",fontsize=8,fontweight="bold")
ax.set_ylim(0,48); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True); ax.tick_params(axis="x",labelsize=7)
save(fig,"units_sold")

# 5 Stock by product stacked by location
prods=["Effective Diet\nPekee","Presha Masala\nPekee","Wild Honey /\nAsali Pekee"]
store=[80,10,5]; mwz=[66,127,6]; dr=[49,169,15]
fig,ax=plt.subplots(figsize=(3.55,2.15)); xx=np.arange(3)
ax.bar(xx,store,color=DG,width=.5,label="Store"); ax.bar(xx,mwz,bottom=store,color=B,width=.5,label="Mwanza")
ax.bar(xx,dr,bottom=np.add(store,mwz),color=A,width=.5,label="Dar")
for i,t in enumerate([195,306,26]): ax.text(i,t+8,str(t),ha="center",fontsize=8,fontweight="bold")
ax.set_xticks(xx); ax.set_xticklabels(prods,fontsize=7); ax.set_ylim(0,350); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=7,ncol=3,loc="upper center",bbox_to_anchor=(.5,1.14)); save(fig,"stock_stacked")

# 6 Produced vs in stock
fig,ax=plt.subplots(figsize=(3.55,2.15)); w=.34
p=[200,350,30]; s=[195,306,26]
b1=ax.bar(xx-w/2,p,w,color="#9CA3AF",label="Produced (all time)"); b2=ax.bar(xx+w/2,s,w,color=G,label="Current stock")
for r in list(b1)+list(b2): ax.text(r.get_x()+r.get_width()/2,r.get_height()+6,int(r.get_height()),ha="center",fontsize=7.5,fontweight="bold")
ax.set_xticks(xx); ax.set_xticklabels(prods,fontsize=7); ax.set_ylim(0,420); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=7,ncol=2,loc="upper center",bbox_to_anchor=(.5,1.14)); save(fig,"prod_vs_stock")

# 7 Branch closing balance grouped
fig,ax=plt.subplots(figsize=(7.1,1.9)); lab=["Full Package","Effective Diet Pekee","Presha Masala Pekee","Wild Honey / Asali"]
mz=[0,66,127,6]; dz=[0,49,169,15]; xx4=np.arange(4); w=.32
b1=ax.bar(xx4-w/2,mz,w,color=G,label="Mwanza"); b2=ax.bar(xx4+w/2,dz,w,color=A,label="Dar es Salaam")
for r in list(b1)+list(b2): ax.text(r.get_x()+r.get_width()/2,r.get_height()+4,int(r.get_height()),ha="center",fontsize=8,fontweight="bold")
ax.set_xticks(xx4); ax.set_xticklabels(lab); ax.set_ylim(0,205); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True)
ax.legend(frameon=False,ncol=2,loc="upper left",fontsize=7); save(fig,"branch_balance")

# 8 Call activity
fig,ax=plt.subplots(figsize=(3.4,2.0))
b=ax.bar(["Instruction","Compliance","Follow-up"],[1,0,0],color=G,width=.45)
ax.text(0,1.03,"1",ha="center",fontweight="bold"); ax.set_ylim(0,1.3); ax.set_yticks([0,1]); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True)
save(fig,"calls")
print("ok")
