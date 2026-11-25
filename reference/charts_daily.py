exec(open("charts.py").read().split("# 1 Sales trend")[0])
# Today vs yesterday stacked by branch
fig,ax=plt.subplots(figsize=(3.4,1.65))
lab=["Tue 24/11","Wed 25/11"]; m=[225000,400000]; d=[200000,640000]
ax.bar(lab,m,color=G,width=.5,label="Mwanza"); ax.bar(lab,d,bottom=m,color=A,width=.5,label="Dar")
for i,t in enumerate([425000,1040000]): ax.text(i,t+25000,f"{t:,}",ha="center",fontsize=7.5,fontweight="bold")
ax.set_ylim(0,1250000); ax.yaxis.set_major_formatter(FuncFormatter(money)); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=7,ncol=2,loc="upper left"); save(fig,"vs_yesterday")
# Units sold today by product & branch
fig,ax=plt.subplots(figsize=(3.4,1.3))
prods=["Full Package","ED Pekee","Presha Masala","Wild Honey"]; mz=[4,0,0,0]; dz=[0,1,23,0]; y=np.arange(4)
ax.barh(y,mz,color=G,height=.5,label="Mwanza"); ax.barh(y,dz,left=mz,color=A,height=.5,label="Dar")
for i,t in enumerate([4,1,23,0]): ax.text(t+.5,i,str(t),va="center",fontsize=8,fontweight="bold")
ax.set_yticks(y); ax.set_yticklabels(prods,fontsize=7.5); ax.invert_yaxis(); ax.set_xlim(0,28); ax.grid(axis="x",color=GRID); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=7,ncol=2,loc="lower right"); save(fig,"units_today")
# closing balance (daily)
fig,ax=plt.subplots(figsize=(3.4,1.65))
b=ax.bar(["Mwanza","Dar es Salaam"],[400000,640000],color=[G,A],width=.55)
for r,v in zip(b,[400000,640000]): ax.text(r.get_x()+r.get_width()/2,v+20000,f"{v:,}",ha="center",fontsize=7.5,fontweight="bold")
ax.yaxis.set_major_formatter(FuncFormatter(money)); ax.set_ylim(0,800000); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True); save(fig,"branch_sales_d")
fig,ax=plt.subplots(figsize=(7.1,1.25)); lab=["Full Package","Effective Diet Pekee","Presha Masala Pekee","Wild Honey / Asali"]
mz=[0,66,127,6]; dz=[0,49,169,15]; xx4=np.arange(4); w=.32
b1=ax.bar(xx4-w/2,mz,w,color=G,label="Mwanza"); b2=ax.bar(xx4+w/2,dz,w,color=A,label="Dar es Salaam")
for r in list(b1)+list(b2): ax.text(r.get_x()+r.get_width()/2,r.get_height()+4,int(r.get_height()),ha="center",fontsize=7.5,fontweight="bold")
ax.set_xticks(xx4); ax.set_xticklabels(lab); ax.set_ylim(0,215); ax.grid(axis="y",color=GRID); ax.set_axisbelow(True); ax.legend(frameon=False,ncol=2,loc="upper left",fontsize=7); save(fig,"branch_balance_d")
print("ok")
