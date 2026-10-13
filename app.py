import hashlib
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from data_utils import demo_csv, load_csv, summarize

st.set_page_config(page_title='교환학생가면 얼마나 쓸까?', page_icon='🌍', layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
.stApp {background:#fafbfc;}
.block-container {padding-top:2rem; max-width:1100px;}
div[data-testid="stMetric"] {background:white; padding:18px; border:1px solid #e2e8f0; border-radius:16px;}
h1,h2,h3 {color:#17243b;}
</style>''', unsafe_allow_html=True)
st.title('교환학생가면 얼마나 쓸까?')
st.caption('어떤 업종에서, 어느 나라에서, 얼마나 썼는지 확인하세요.')

with st.sidebar:
    st.header('분석할 내역')
    upload = st.file_uploader('해외승인내역 CSV 업로드', type=['csv'])
    demo = st.checkbox('가상 샘플 데이터로 보기', value=False)
    st.caption('기본 화면은 공개용 실제 내역입니다. 업로드한 파일은 메모리에서 분석하며 별도로 저장하지 않습니다.')

if upload is not None:
    content = upload.getvalue()
elif demo:
    content = demo_csv()
    st.info('현재 화면은 가상 샘플 데이터입니다.')
else:
    data_path = Path(__file__).resolve().parent / 'public_data.csv'
    if not data_path.exists():
        st.error('public_data.csv를 앱과 같은 폴더에 포함해 주세요.')
        st.stop()
    content = data_path.read_bytes()
    st.caption('공개용 실제 데이터 · 가맹점은 익명 처리했으며 카드번호·승인번호·거래시각은 포함하지 않았습니다.')
try:
    df, notices = load_csv(content)
except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
    st.error(str(error))
    st.stop()

file_key = hashlib.sha256(content).hexdigest()[:12]
with st.sidebar:
    st.header('필터')
    bounds = (df['거래일'].min().date(), df['거래일'].max().date())
    dates = st.date_input('거래 기간', value=bounds, min_value=bounds[0], max_value=bounds[1], key=f'dates_{file_key}')
    countries = st.multiselect('국가', sorted(df['국가'].unique()), default=sorted(df['국가'].unique()), key=f'countries_{file_key}')
    categories = st.multiselect('업종', sorted(df['업종'].unique()), default=sorted(df['업종'].unique()), key=f'categories_{file_key}')
    st.caption('소비 차트는 정상 상태의 양수 승인액을 집계합니다. 취소 건은 차감하지 않고 별도로 표시합니다.')
if len(dates) != 2:
    st.info('시작일과 종료일을 선택해 주세요.')
    st.stop()
filtered = df.loc[(df['거래일'].dt.date >= dates[0]) & (df['거래일'].dt.date <= dates[1]) & df['국가'].isin(countries) & df['업종'].isin(categories)].copy()
if filtered.empty:
    st.info('선택한 조건에 맞는 거래가 없어요. 기간·국가·업종 필터를 조정해 주세요.')
    st.stop()
spend = filtered.loc[(filtered['상태'] == '정상') & (filtered['원화금액'] > 0)]
canceled = filtered.loc[filtered['취소여부']]
other = filtered.loc[~filtered.index.isin(spend.index) & ~filtered.index.isin(canceled.index)]
total = spend['원화금액'].sum()
cols = st.columns(3)
cols[0].metric('정상 승인 합계', f'{total:,.0f}원')
cols[1].metric('정상 승인 건수', f'{len(spend):,}건')
cols[2].metric('건당 평균 승인액', f'{total / len(spend):,.0f}원' if len(spend) else '—')
st.caption('원화 환산 승인액 기준입니다. 실제 청구액·최종 순지출과 다를 수 있으며 현지 통화 금액은 합산하지 않습니다.')
if len(other):
    st.warning(f'상태가 정상이 아니거나 금액이 0 이하인 {len(other)}건은 소비 차트에서 제외했습니다. 상세 내역에서 확인할 수 있어요.')

palette = ['#3063a6', '#4d78b0', '#678dbb', '#82a1c6', '#9bb5d1', '#b5c9dd', '#cfdde9', '#e3e9ef']


def chart(fig):
    fig.update_layout(font=dict(family='Arial, sans-serif'), margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, width='stretch')


overview, trend, details = st.tabs(['업종과 국가', '소비 흐름', '상세 내역'])
with overview:
    if spend.empty:
        st.info('정상 상태의 양수 승인 내역이 없어 소비 차트를 표시할 수 없어요.')
    else:
        st.subheader('업종별 소비 트리맵')
        by_category = summarize(spend, '업종')
        tree = by_category.head(7)[['업종', '원화금액']].copy()
        if len(by_category) > 7:
            tree = pd.concat([tree, pd.DataFrame([{'업종': '그 외 업종', '원화금액': by_category.iloc[7:]['원화금액'].sum()}])], ignore_index=True)
        fig = px.treemap(tree, path=['업종'], values='원화금액', color='업종', color_discrete_sequence=palette)
        fig.update_traces(textinfo='label+percent root', hovertemplate='%{label}<br>%{value:,.0f}원<extra></extra>')
        fig.update_layout(height=380)
        chart(fig)
        st.caption('큰 영역일수록 승인액이 큽니다. 상위 7개 업종을 표시하고 나머지는 묶었습니다.')
        top = by_category.iloc[0]
        st.info(f'가장 큰 소비 업종은 {top["업종"]}입니다. {top["원화금액"]:,.0f}원으로 정상 승인액의 {top["원화금액"] / total:.1%}를 차지해요.')
        with st.expander('업종별 전체 금액 보기'):
            st.dataframe(by_category.assign(비중=by_category['원화금액'] / total), hide_index=True, width='stretch', column_config={'원화금액': st.column_config.NumberColumn('원화 승인액', format='%,d원'), '비중': st.column_config.NumberColumn('비중', format='percent')})
        with st.expander('국가별 소비 보기'):
            chart(px.bar(summarize(spend, '국가').sort_values('원화금액'), x='원화금액', y='국가', orientation='h', color_discrete_sequence=palette, labels={'원화금액': '원화 승인액'}))
with trend:
    if not spend.empty:
        st.subheader('월별 승인액')
        monthly = spend.groupby('월', as_index=False)['원화금액'].sum()
        chart(px.bar(monthly, x='월', y='원화금액', color_discrete_sequence=palette, labels={'원화금액': '원화 승인액'}))
        st.subheader('일별 승인액')
        daily = spend.groupby('거래일')['원화금액'].sum().reindex(pd.date_range(dates[0], dates[1]), fill_value=0).rename_axis('거래일').reset_index()
        chart(px.line(daily, x='거래일', y='원화금액', labels={'원화금액': '원화 승인액'}))
        st.subheader('가맹점별 승인액 상위 10곳')
        chart(px.bar(summarize(spend, '가맹점명').head(10).sort_values('원화금액'), x='원화금액', y='가맹점명', orientation='h', text_auto=',.0f', labels={'원화금액': '원화 승인액'}))
    else:
        st.info('소비 흐름을 표시할 정상 승인 내역이 없어요.')
with details:
    st.subheader('선택한 기간의 내역')
    st.caption(f'취소 {len(canceled):,}건 · 기타 상태·금액 {len(other):,}건')
    mode = st.radio('표시할 거래', ['전체', '정상 양수 승인', '취소', '기타 상태·금액'], horizontal=True)
    view = {'전체': filtered, '정상 양수 승인': spend, '취소': canceled, '기타 상태·금액': other}[mode].copy()
    query = st.text_input('가맹점 검색')
    if query:
        view = view.loc[view['가맹점명'].str.contains(query, case=False, regex=False, na=False)]
    columns = ['거래일', '거래시각', '가맹점명', '업종', '국가', '원화금액', '현지금액', '통화', '상태']
    display = view[columns].sort_values('거래일', ascending=False)
    st.dataframe(display, hide_index=True, width='stretch')
    export = display.copy()
    export['거래일'] = export['거래일'].dt.strftime('%Y-%m-%d')
    # Prevent merchant strings from becoming formulas when opened in a spreadsheet.
    for col in export.select_dtypes(include='object').columns:
        export[col] = export[col].map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value)
    st.download_button('현재 내역 CSV 다운로드', export.to_csv(index=False).encode('utf-8-sig'), 'filtered_overseas.csv', 'text/csv')
    st.caption('카드번호와 승인번호는 화면 및 다운로드에서 제외합니다.')
