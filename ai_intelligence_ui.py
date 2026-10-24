"""All AI research stays in the backstage; never manufactures progress or accuracy."""
import json
import pandas as pd
import altair as alt
import streamlit as st
from terminal_ui import section
from ai_model_lab import load_lab,CONTEXT_FIELDS,FAMILIES
from ai_context_features import extract
from ai_diagnostics import health,reliability
from strategy_learning import load

LABELS={'technical-logistic':'技術邏輯模型','technical-naive-bayes':'技術高斯貝氏','regime-logistic':'行情專屬邏輯模型','news-logistic':'技術＋新聞詞彙','funding-logistic':'技術＋資金背景','context-logistic':'技術＋全部背景'}
REGIMES={'trend_up':'上升趨勢','trend_down':'下降趨勢','range':'盤整','high_volatility':'高波動','mixed':'過渡'}


def intelligence_panel(db,profile,mode,rows):
    section('AI強化實驗室','REGIME · DRIFT · FEATURES · MODELS · CALIBRATION')
    current=load(db,profile,mode);lab=load_lab(db,profile,mode)
    st.caption('AI研究最近檢查（台北） '+pd.Timestamp(lab['updated_at']).tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M:%S') if lab.get('updated_at') else '等待背景AI研究；請保持新版啟動程序運作。')
    models=[m for m in [current.get('incumbent'),current.get('challenger'),*lab.get('contenders',[])] if m]
    unique={m['id']:m for m in models}
    if not unique:
        st.info('尚無策略模型。先累積200筆合格未來結算；多模型實驗另需至少300筆及完整資料切分，不能把文字摘要當成已訓練模型。')
        chosen=None
    else:
        chosen=st.selectbox('AI診斷模型',list(unique),format_func=lambda key:LABELS.get(unique[key].get('family'),'原策略邏輯模型')+' · '+key,key='ai-diagnostic-'+profile)
    tabs=st.tabs(['行情適配','退化監控','新聞與資金驗證','多模型研究','可信度校準'])
    if chosen:
        h=health(rows,chosen);cal=reliability(rows,chosen)
    else:h={'regimes':[],'status':'insufficient','reasons':[],'recent_samples':0,'previous_samples':0,'recent_mean_r':None,'previous_mean_r':None,'recent_brier':None,'previous_brier':None,'recent_interval95_r':[None,None]};cal={'samples':0,'bins':[],'brier':None,'raw_brier':None,'ece':None,'calibrated_samples':0}
    with tabs[0]:
        st.caption('各行情只看模型事前選中的未來結算；至少30筆、10個結算日才判斷支持或避開；尚無正向證據的行情也先觀察，不發布合格新訊號。高波動可能因原策略排除而沒有樣本，未知不等於適合交易。')
        if h['regimes']:
            st.dataframe(pd.DataFrame([{'行情':REGIMES[r['regime']],'樣本':r['samples'],'交易日':r['days'],'平均淨R':r['mean_r'],'狀態':{'avoid':'暫避','supported':'有正向證據','observe':'觀察／不足'}[r['state']]} for r in h['regimes']]),hide_index=True,width='stretch')
        else:st.info('尚無行情適配證據。')
    with tabs[1]:
        label={'degraded':'退化警示，暫停合格訊號','monitoring':'監測中，尚未觸發退化條件','insufficient':'樣本不足，不能判定健康'}[h['status']]
        st.warning(label) if h['status']=='degraded' else st.info(label)
        a,b,c=st.columns(3);a.metric('近期／先前選擇樣本',f'{h["recent_samples"]} / {h["previous_samples"]}')
        b.metric('近期每筆淨R',f'{h["recent_mean_r"]:+.3f}' if h['recent_mean_r'] is not None else '尚無樣本')
        c.metric('先前每筆淨R',f'{h["previous_mean_r"]:+.3f}' if h['previous_mean_r'] is not None else '尚無樣本')
        for reason in h['reasons']:st.caption('• '+reason)
        st.caption('近期30筆對照之前最多60筆；至少各30筆與近期10個結算日。近期淨R群聚區間上限小於0，或Brier增加≥0.1且淨R變差轉負，會阻擋合格Telegram及前台入場候選。原始模擬仍繼續；證據改善後重新評估，不自動平倉。')
    with tabs[2]:
        snapshots=[extract(r) for r in rows]
        available=[k for k in (snapshots[0]['values'] if snapshots else []) if k.endswith('available')]
        st.dataframe(pd.DataFrame([{'事前特徵組':k,'可用筆數':sum(bool(s['values'][k]) for s in snapshots),'總紀錄':len(rows)} for k in available]),hide_index=True,width='stretch')
        reports=lab.get('ablations',[])
        if reports:
            st.dataframe(pd.DataFrame([{'加入特徵':LABELS[r['family']],'共同未來機會':r['common'],'每機會淨R差':r['delta_mean_r'],'修正區間下限':r['delta95_r'][0],'研究條件通過':r['comparison_pass']} for r in reports]),hide_index=True,width='stretch')
        else:st.info('新聞／資金對照尚無共同未來證據；不宣稱加入資訊已提高獲利。')
        st.caption('固定比較技術基準與新聞、資金、全部背景三組。新聞為事前標題與固定英文詞彙，不是全文語意因果分析；穩定幣供給與OI不是淨資金流。新取得資料不回填舊預測。')
    with tabs[3]:
        contenders=lab.get('contenders',[])
        st.write(f'平行候選 {len(contenders)} / 最多{len(FAMILIES)} 類')
        if contenders:st.dataframe(pd.DataFrame([{'家族':LABELS[m['family']],'模型':m['id'],'來源樣本':m['source_count'],'校準器':'已建立' if m.get('calibrator') else '樣本不足，保留原分數','訓練時間UTC':m['trained_at']} for m in contenders]),hide_index=True,width='stretch')
        if not contenders and lab.get('competitions'):st.caption('以下為最近完成輪次快照，非目前平行候選。')
        for report in lab.get('competitions',[]):
            with st.expander(LABELS[report['family']]+' · '+str(report['common'])+'筆共同機會'):
                st.dataframe(pd.DataFrame([{'比較條件':k,'通過':v} for k,v in report['checks'].items()]),hide_index=True,width='stretch')
                st.caption(f'固定9項比較的Bonferroni近似區間 {report.get("confidence_pct",0):.2f}%；候選自身獲利資格：{report["qualified"]}')
        if lab.get('attempts'):st.dataframe(pd.DataFrame(lab['attempts'][-24:]),hide_index=True,width='stretch')
        if lab.get('round_history'):
            with st.expander('研究輪次與升級決策'):st.json(lab['round_history'],expanded=False)
        st.caption('至少300筆合格結算後研究；每輪後需72小時與40筆新結算。時間分割60%訓練／10%校準／10%選門檻／20%保留測試，隔離跨界標籤。所有候選共同未來樣本充分後才決策，90日不足則結束觀察；沒有回測直接替換。')
    with tabs[4]:
        a,b,c=st.columns(3)
        a.metric('未來分數樣本',cal['samples']);b.metric('Brier誤差',f'{cal["brier"]:.4f}' if cal['brier'] is not None else '尚無樣本');c.metric('已校準預測筆數',cal['calibrated_samples'])
        if cal['bins']:
            f=pd.DataFrame(cal['bins']);st.dataframe(f,hide_index=True,width='stretch')
            chart=f.melt(['分數區間','筆數','樣本足夠'],value_vars=['平均預測','觀察獲利比例'],var_name='類型',value_name='比例')
            st.altair_chart(alt.Chart(chart).mark_line(point=True).encode(x='分數區間:O',y=alt.Y('比例:Q',scale=alt.Scale(domain=[0,1])),color='類型:N',tooltip=['分數區間','類型','比例','筆數']),width='stretch')
        if chosen and not unique[chosen].get('calibrator'):st.caption('這個模型沒有校準器，以上只評估原始分數，沒有事後改寫舊預測。')
        st.caption('新候選只用獨立的過去校準段建立Platt映射；未來逐筆保存原分數、校準分數與棄權理由。分箱不足20筆不當作可靠勝率。模型遇未知行情、嚴重分布外特徵或必要背景缺漏時棄權；校準不保證獲利。')
    st.download_button('匯出AI強化研究證據',json.dumps({'lab':lab,'health':h,'reliability':cal},ensure_ascii=False,indent=2),file_name=profile+'-ai-intelligence.json',mime='application/json')
