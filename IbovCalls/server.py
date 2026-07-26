from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os
import concurrent.futures

app = Flask(__name__, static_folder='.')
CORS(app)


@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route('/')
def serve_html():
    return send_from_directory('.', 'index.html')


@app.route('/acoes')
def serve_stocks_html():
    return send_from_directory('.', 'acoes.html')

@app.route('/api/ibov')
def get_ibov_data():
    range_param = request.args.get('range', '1y')
    period_map = {
        '3mo': '3mo', '6mo': '6mo', '1y': '1y', '2y': '2y',
        'ytd': 'ytd', 'max': 'max'
    }
    period = period_map.get(range_param, '6mo')

    try:
        ibov = yf.Ticker('^BVSP')
        hist = ibov.history(period=period, interval='1d')

        if hist.empty:
            return jsonify({'error': 'No data returned from Yahoo Finance'}), 500

        hist = hist.reset_index()
        data = []
        for _, row in hist.iterrows():
            ts = row['Date']
            if isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()

            data.append({
                'date': ts.strftime('%Y-%m-%d'),
                'open': round(float(row['Open']), 2),
                'high': round(float(row['High']), 2),
                'low': round(float(row['Low']), 2),
                'close': round(float(row['Close']), 2),
                'volume': int(row['Volume'])
            })

        quote = ibov.history(period='5d', interval='1d')
        current_price = None
        change = None
        change_pct = None
        if not quote.empty:
            last = quote.iloc[-1]
            current_price = round(float(last['Close']), 2)
            if len(quote) > 1:
                prev_close = round(float(quote.iloc[-2]['Close']), 2)
                change = round(current_price - prev_close, 2)
                change_pct = round((change / prev_close) * 100, 2)
            else:
                change = 0
                change_pct = 0

        return jsonify({
            'data': data,
            'current': {
                'price': current_price or data[-1]['close'],
                'change': change,
                'changePercent': change_pct
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/calls')
def get_calls():
    calls = [
        {"date":"2024-11-18","bank":"Morgan Stanley","title":"Rebaixa Brasil para underweight \u2014 'Pode piorar antes de melhorar'","summary":"Morgan Stanley cortou recomenda\u00e7\u00e3o de neutro para underweight (equivalente a venda) para a\u00e7\u00f5es brasileiras, citando que os riscos fiscais superam a atratividade do valuation. Projeta Ibovespa em 146k pontos no cen\u00e1rio-base para fim de 2025 (bull: 160k; bear: 105k). 'Pode piorar antes de melhorar.' Com juros longos entre 12-14% ao ano, a renda fixa compete diretamente com as a\u00e7\u00f5es. Alerta para risco de domin\u00e2ncia fiscal \u2014 situa\u00e7\u00e3o em que o descontrole das contas p\u00fablicas torna a pol\u00edtica monet\u00e1ria ineficaz no controle da infla\u00e7\u00e3o.","url":"https://exame.com/invest/mercados/morgan-stanley-rebaixa-acoes-do-brasil-e-alerta-sobre-sufoco-no-fiscal/"},
        {"date":"2024-11-26","bank":"JP Morgan","title":"Rebaixa Brasil para neutro \u2014 'Dia da Marmota' fiscal","summary":"JP Morgan rebaixou Brasil de overweight para neutro, elevando M\u00e9xico de neutro para overweight em seu lugar. Banco afirmou que o Brasil vive o 'Dia da Marmota' com o debate fiscal: 'nos \u00faltimos dois anos, o mercado teve surtos de preocupa\u00e7\u00e3o com o fiscal, depois o governo faz algo para apaziguar o cen\u00e1rio at\u00e9 que uma manchete sobre o fiscal aparece novamente'. Cita sa\u00edda de mais de R$30bi de estrangeiros em 2024, hedge funds em resgate e perspectiva de novas altas da Selic em 2025 como agravantes.","url":"https://www.infomoney.com.br/mercados/jpmorgan-rebaixa-brasil-ao-ver-mais-do-mesmo-e-agora-prefere-acoes-do-mexico-na-al/"},
        {"date":"2025-01-03","bank":"BTG Pactual","title":"In\u00edcio cauteloso para 2025","summary":"BTG come\u00e7ou 2025 com recomenda\u00e7\u00e3o cautelosa. Cen\u00e1rios Ibovespa: 90k (bear), 147k (base), 179k (bull). 'In\u00edcio de 2025 dif\u00edcil para as a\u00e7\u00f5es brasileiras' devido ao cen\u00e1rio fiscal incerto. Portfolio 10SIM defensivo.","url":"https://www.estadao.com.br/einvestidor/cenarios-e-mercado/btg-pactual-bolsa-de-valores-b3-2025-o-que-esperar-acoes-brasileiras/"},
        {"date":"2025-01-06","bank":"JP Morgan","title":"Proje\u00e7\u00e3o conservadora: Ibovespa 135k","summary":"JP Morgan estimou Ibovespa em 135k pontos no fim de 2025, vis\u00e3o conservadora. Preocupa\u00e7\u00e3o com situa\u00e7\u00e3o fiscal e risco de 'abrir os cofres' antes das elei\u00e7\u00f5es de 2026. Pr\u00eamio de risco deve dificultar reavalia\u00e7\u00e3o de pre\u00e7os.","url":"https://valorinternational.globo.com/markets/news/2025/01/06/brazils-ibovespa-could-reach-142000-points-by-late-2025.ghtml"},
        {"date":"2025-01-14","bank":"Ita\u00fa BBA","title":"Reduziu alvo do Ibovespa para 145k","summary":"Ita\u00fa BBA reduziu proje\u00e7\u00e3o de 165k para 145k pontos. Motivos: custo de capital mais elevado, juros altos, infla\u00e7\u00e3o crescente e c\u00e2mbio elevado. Valuation de 6,7x P/L favor\u00e1vel. Portfolio defensivo com exportadoras e utilities.","url":"https://valor.globo.com/financas/noticia/2025/01/14/ita-bba-reduz-projeo-do-preo-alvo-do-ibovespa-para-145-mil-pontos-no-fim-de-2025.ghtml"},
        {"date":"2025-02-12","bank":"BofA","title":"Manteve overweight Brasil - 19 a\u00e7\u00f5es","summary":"BofA manteve overweight para Brasil no MSCI LatAm. 19 a\u00e7\u00f5es brasileiras na carteira. Prefer\u00eancia por bancos (Ita\u00fa, BTG, Bradesco), seguradoras, prote\u00ednas (JBS), construtoras e ind\u00fastrias globais (Embraer). Selic pico de 15,25%.","url":"https://www.seudinheiro.com/2025/bolsa-dolar/bofa-mantem-recomendacao-comprar-brasil-19-acoes-b3-carteira-acao-eletrica-queridinha-bolsa-novidade-lecm/"},
        {"date":"2025-03-10","bank":"JP Morgan","title":"Elevou Brasil para overweight (compra)","summary":"JP Morgan elevou recomenda\u00e7\u00e3o de neutro para overweight. Citou 'mudan\u00e7a de regime' nas elei\u00e7\u00f5es 2026, valuations atraentes, fim do ciclo de aperto monet\u00e1rio. Rebaixou M\u00e9xico de compra para neutro. Aloca\u00e7\u00e3o defensiva em bancos e utilities.","url":"https://valor.globo.com/financas/noticia/2025/03/10/jp-morgan-eleva-recomendao-para-a-bolsa-brasileira-e-cita-mudana-de-regime-nas-eleies-de-2026.ghtml"},
        {"date":"2025-04-01","bank":"BTG Pactual","title":"10SIM - Adicionando risco gradualmente","summary":"BTG manteve estrat\u00e9gia de adicionar risco gradualmente. Ibovespa subiu 5,9% em mar\u00e7o. Foco em empresas de alta qualidade. Exposi\u00e7\u00e3o a exportadores reduzida de 30% para 20%. Nubank substitui B3 no setor financeiro.","url":"https://content.btgpactual.com/research/files/file/2025-04-01T082756.063_BTG%2010SIM%20ABR25.pdf"},
        {"date":"2025-05-12","bank":"BofA","title":"Manteve overweight - Adicionou Copel","summary":"BofA manteve otimismo com a\u00e7\u00f5es brasileiras. Adicionou Copel ao portf\u00f3lio, excluiu Gerdau. Acredita que juros mais baixos turbinar\u00e3o crescimento dos lucros. A\u00e7\u00f5es brasileiras ex-commodities negociam com desconto de 13% vs hist\u00f3rico.","url":"https://valor.globo.com/financas/noticia/2025/05/12/bofa-mantm-otimismo-com-bolsa-brasileira-e-adiciona-copel-ao-portflio.ghtml"},
        {"date":"2025-05-20","bank":"Morgan Stanley","title":"Elevou para overweight - Ibovespa target 189k","summary":"Morgan Stanley elevou recomenda\u00e7\u00e3o de equal-weight para overweight. Projeta Ibovespa em 189k meados de 2026 (+36%). Citou in\u00edcio de mudan\u00e7a pol\u00edtica, pico de juros. A\u00e7\u00f5es: Petrobras, Eletrobras, Nubank, Ita\u00fa, B3, JBS. 21 a\u00e7\u00f5es no portf\u00f3lio.","url":"https://valor.globo.com/financas/noticia/2025/05/20/morgan-stanley-v-ibovespa-em-189-mil-pontos-em-meados-de-2026-e-cita-incio-de-mudana-poltica-no-brasil.ghtml"},
        {"date":"2025-06-04","bank":"Goldman Sachs","title":"Manteve compra BTG, elevou XP, cortou B3","summary":"Goldman Sachs manteve compra para BTG Pactual ('hist\u00f3ria de lucros mais resiliente'), elevou XP Inc de neutra para compra, rebaixou B3 de compra para neutra ap\u00f3s alta de 35% no ano. B3 enfrenta riscos competitivos e jur\u00eddicos.","url":"https://exame.com/invest/mercados/em-meio-a-recordes-do-ibovespa-goldman-rebaixa-recomendacao-para-acoes-da-b3/"},
        {"date":"2025-06-11","bank":"BofA","title":"Cortou Brasil para neutro - 1\u00aa vez em 3 anos","summary":"BofA rebaixou Brasil de overweight para marketweight (neutro) pela 1\u00aa vez em 3 anos. Motivos: perda de tra\u00e7\u00e3o nos gatilhos dom\u00e9sticos, cautela com petr\u00f3leo e min\u00e9rio de ferro. Risco de euforia - 67% das a\u00e7\u00f5es acima da m\u00e9dia m\u00f3vel de 200 dias.","url":"https://valor.globo.com/financas/noticia/2025/06/11/bofa-rebaixa-recomendao-das-aes-brasileiras-para-neutra-pela-1-vez-em-trs-anos.ghtml"},
        {"date":"2025-07-18","bank":"Goldman Sachs","title":"Economia brasileira 'fora de sincronia' \u2014 exige ajuste fiscal estrutural permanente","summary":"Goldman Sachs afirmou que a economia brasileira est\u00e1 'fora de sincronia' e requer um grande ajuste fiscal estrutural permanente para evitar desequil\u00edbrios dom\u00e9sticos e externos crescentes. Banco argumenta que juros altos isolados n\u00e3o s\u00e3o suficientes: sem consolida\u00e7\u00e3o das contas p\u00fablicas, o pr\u00eamio de risco exigido nos ativos dom\u00e9sticos tende a permanecer elevado. D\u00edvida bruta do governo geral havia atingido 78,7% do PIB ao fim de 2025, em trajet\u00f3ria ascendente desde 71,7% em 2022.","url":"https://www.cnnbrasil.com.br/economia/macroeconomia/economia-brasileira-esta-fora-de-sincronia-e-exige-grande-ajuste-estrutural-diz-goldman-sachs/"},
        {"date":"2025-07-08","bank":"Ita\u00fa BBA","title":"Elevou proje\u00e7\u00e3o para 155k","summary":"Ita\u00fa BBA elevou proje\u00e7\u00e3o de 145k para 155k. Motivos: custo de capital mais baixo, precifica\u00e7\u00e3o de ciclo de cortes de juros. Prefer\u00eancia por utilities (Equatorial, Sabesp), sa\u00fade (Rede D'Or), bancos (BTG, Bradesco). Primeiro corte Selic esperado para 1\u00ba tri 2026.","url":"https://valor.globo.com/financas/noticia/2025/07/08/ita-bba-eleva-projeo-do-ibovespa-para-155-mil-pontos-ao-fim-de-2025.ghtml"},
        {"date":"2025-08-01","bank":"BTG Pactual","title":"10SIM - Reduzindo beta; Sabesp substitui Copel","summary":"BTG reduziu beta da carteira 10SIM. Sabesp substituiu Copel (TIR real de 10%). Motiva e Multiplan substitu\u00edram Rumo e Cyrela. Vibra entra no lugar da Cosan. Cen\u00e1rio geopol\u00edtico turbulento.","url":"https://content.btgpactual.com/research/files/file/2025-08-01T083542.842_BTG%2010SIM%20AGO25.pdf"},
        {"date":"2025-08-25","bank":"BTG Pactual","title":"Elevou recomenda\u00e7\u00e3o para acima do benchmark","summary":"BTG elevou recomenda\u00e7\u00e3o para Brasil acima do benchmark. Recomenda sa\u00edda gradual da renda fixa para a\u00e7\u00f5es. Projeta primeiro corte da Selic no 1\u00ba tri 2026. Infla\u00e7\u00e3o mais baixa e atividade mais fraca sinalizam queda de juros.","url":"https://www.seudinheiro.com/2025/bolsa-dolar/e-hora-de-voltar-para-as-acoes-brasileiras-expectativa-de-queda-dos-juros-leva-btg-a-recomendar-saida-gradual-da-renda-fixa-mlim/"},
        {"date":"2025-08-26","bank":"Goldman Sachs","title":"Brasil \u00e9 lugar atraente para alocar capital","summary":"John Waldron, presidente do Goldman Sachs, visitou Brasil e afirmou que o pa\u00eds \u00e9 'lugar atraente para alocar capital'. Destacou juros reais elevados, economia resiliente e valuations atrativos. Goldman celebra 30 anos no Brasil.","url":"https://valorinternational.globo.com/markets/news/2025/08/26/brazil-is-an-attractive-place-to-allocate-capital-goldman-sachs-says.ghtml"},
        {"date":"2025-08-29","bank":"JP Morgan","title":"Manteve compra para bolsa local","summary":"JP Morgan manteve recomenda\u00e7\u00e3o de compra para a\u00e7\u00f5es brasileiras. Atento ao potencial do in\u00edcio do ciclo de cortes de juros em dezembro e ao cen\u00e1rio eleitoral de 2026. Retirou Banco do Brasil do portf\u00f3lio modelo.","url":"https://valor.globo.com/financas/noticia/2025/08/29/jp-morgan-mantm-compra-para-bolsa-local-e-retira-aes-do-bb-de-portflio-modelo.ghtml"},
        {"date":"2025-10-01","bank":"BTG Pactual","title":"10SIM - Ciclos de flexibiliza\u00e7\u00e3o monet\u00e1ria","summary":"BTG: ciclos de flexibiliza\u00e7\u00e3o nos EUA e Brasil devem apoiar a\u00e7\u00f5es. Localiza substitui Motiva. Copel substitui Equatorial. Projeta primeiro corte Selic em janeiro 2026, redu\u00e7\u00e3o de 300bps em 2026. Selic terminal de 12%.","url":"https://content.btgpactual.com/research/files/file/2025-10-01T084238.835_BTG%2010SIM%20OUT25.pdf"},
        {"date":"2025-10-24","bank":"Morgan Stanley","title":"Recomenda financeiras antes do corte de juros","summary":"Morgan Stanley recomenda financeiras (XP, BTG, B3) antes do ciclo de flexibiliza\u00e7\u00e3o. Projeta 350bps de cortes a partir de mar\u00e7o 2026. Selic pode cair de 15% para 11,5% at\u00e9 fim de 2026. US$14bi em novos aportes para fundos de a\u00e7\u00f5es.","url":"https://www.bloomberglinea.com.br/2025/10/24/morgan-stanley-recomenda-investir-nestas-acoes-ante-possivel-corte-de-juros-no-brasil/"},
        {"date":"2025-10-29","bank":"JP Morgan","title":"Projeta Ibovespa a 155k at\u00e9 fim de 2025","summary":"JPMorgan projeta Ibovespa em 155k pontos at\u00e9 fim de 2025. Impulsionado por cortes de juros no Brasil e EUA, melhora no com\u00e9rcio China-Brasil. Projeta ciclo de afrouxamento de 425 pontos-base.","url":"https://einvestidor.estadao.com.br/ultimas/jpmorgan-projeta-ibovespa-155-mil-pontos-corte-juros-cenario-global/"},
        {"date":"2025-11-12","bank":"Goldman Sachs","title":"Disciplina fiscal crucial p\u00f3s-elei\u00e7\u00e3o 2026","summary":"Goldman Sachs: disciplina fiscal ser\u00e1 prioridade m\u00e1xima a partir de 2027, independentemente do resultado eleitoral. Brasil precisa de super\u00e1vit prim\u00e1rio acima de 2,5% do PIB. Ajuste fiscal de 3pp do PIB ainda necess\u00e1rio.","url":"https://www.reuters.com/world/americas/brazils-fiscal-discipline-crucial-post-2026-election-warns-goldman-sachs-2025-11-12/"},
        {"date":"2025-11-17","bank":"Morgan Stanley","title":"Projeta Ibovespa a 200k fim 2026","summary":"Morgan Stanley projeta Ibovespa em 200k pontos fim 2026. Mant\u00e9m overweight. Brasil pode se tornar destaque global em redu\u00e7\u00e3o do custo de capital. Risco: juros altos por mais tempo devido a impulso fiscal.","url":"https://valor.globo.com/financas/noticia/2025/11/17/morgan-stanley-projeta-ibovespa-a-200-mil-pontos-no-fim-de-2026-com-queda-de-juros.ghtml"},
        {"date":"2025-12-01","bank":"BTG Pactual","title":"10SIM - Flexibiliza\u00e7\u00e3o prestes a come\u00e7ar","summary":"BTG: ciclo de flexibiliza\u00e7\u00e3o prestes a come\u00e7ar no Brasil. Ibovespa subiu 6% em novembro. Projeta primeiro corte em janeiro 2026, redu\u00e7\u00e3o total de 300bps. Eneva entra na carteira. Exposi\u00e7\u00e3o a construtoras, Localiza, Rede D'Or e Embraer.","url":"https://content.btgpactual.com/research/files/file/2025-12-01T085135.567_BTG%2010SIM%20DEZ25.pdf"},
        {"date":"2025-12-02","bank":"JP Morgan","title":"Projeta Ibovespa a 190k fim 2026","summary":"JPMorgan projeta Ibovespa em 190k pontos fim 2026 (+19%). Overweight em Brasil. Cen\u00e1rios bin\u00e1rios com elei\u00e7\u00e3o: otimista 230k, pessimista 120k. Corte de 350-400bps na Selic. Elei\u00e7\u00e3o ser\u00e1 'bin\u00e1ria' e apertada.","url":"https://www.infomoney.com.br/mercados/jpmorgan-projeta-ibovespa-a-190-mil-pontos-em-2026-e-ve-cenarios-binarios-com-eleicao/"},
        {"date":"2025-12-17","bank":"Ita\u00fa BBA","title":"Projeta Ibovespa 165k-180k para 2026","summary":"Ita\u00fa BBA v\u00ea Ibovespa entre 165k e 180k em 2026. Bull case: 189k. Motores: cortes de juros no Brasil e EUA, infla\u00e7\u00e3o mais fraca, fluxo estrangeiro de R$30bi. Financeiros, energia el\u00e9trica, saneamento e constru\u00e7\u00e3o civil como destaques.","url":"https://valorinveste.globo.com/mercados/renda-variavel/bolsas-e-indices/noticia/2025/12/17/ibovespa-pode-subir-ate-17percent-em-2026-itau-bba-revela-setores-favoritos.ghtml"},
        {"date":"2026-01-02","bank":"BTG Pactual","title":"10SIM - Ano promissor mas turbulento","summary":"BTG: 2026 promissor mas turbulento. A\u00e7\u00f5es brasileiras apoiadas por flexibiliza\u00e7\u00e3o monet\u00e1ria. Ita\u00fa e Raia substituem Smartfit e Copel. Aura substitui Direcional. Cen\u00e1rio bull: Ibovespa 186k (P/L 12x). Elei\u00e7\u00f5es trazem volatilidade.","url":"https://content.btgpactual.com/research/files/file/2026-01-02T084021.756_BTG%2010SIM%20JAN26.pdf"},
        {"date":"2026-01-12","bank":"BofA","title":"Elevou Brasil para overweight - 'Cortes profundos'","summary":"BofA elevou Brasil de marketweight para overweight. 'Cortes profundos de juros para quem esperou'. Ciclo de afrouxamento ser\u00e1 o principal motor. Brasil tem uma das maiores correla\u00e7\u00f5es com queda de juros entre emergentes. Adicionou RD Sa\u00fade e Anima.","url":"https://www.infomoney.com.br/mercados/bofa-eleva-brasil-a-compra-com-aposta-em-cortes-profundos-nos-juros-e-muda-carteira/"},
        {"date":"2026-01-13","bank":"Goldman Sachs","title":"2026 s\u00f3lido para bancos brasileiros","summary":"Goldman Sachs v\u00ea 2026 s\u00f3lido para bancos brasileiros. Preferidos: Nubank, BTG (target R$63), Inter e Ita\u00fa. Projeta crescimento do cr\u00e9dito de 9,5% em 2026. Qualidade dos ativos deve se manter est\u00e1vel. FGC ap\u00f3s liquida\u00e7\u00e3o do Banco Master 'administr\u00e1vel'.","url":"https://www.infomoney.com.br/mercados/goldman-sachs-projeta-2026-solido-para-bancos-brasileiros-e-destaca-acoes-preferidas/"},
        {"date":"2026-01-14","bank":"Ita\u00fa BBA","title":"Projeta Ibovespa a 185k em 2026","summary":"Ita\u00fa BBA elevou proje\u00e7\u00e3o para 185k pontos fim 2026. Mant\u00e9m overweight. Ibovespa avan\u00e7ou 34% em reais em 2025. Valuation abaixo da m\u00e9dia dos emergentes. Projeta Selic em 12,75% no fim de 2026 (225bps de cortes). A\u00e7\u00f5es preferidas: Equatorial, BTG, Prio, Suzano.","url":"https://valor.globo.com/financas/noticia/2026/01/14/itau-bba-projeta-ibovespa-em-185-mil-pontos-neste-ano.ghtml"},
        {"date":"2026-01-22","bank":"JP Morgan","title":"Fluxo emergentes pode trazer US$25bi ao Brasil","summary":"JP Morgan: retorno de aloca\u00e7\u00e3o global \u00e0 m\u00e9dia hist\u00f3rica pode destravar US$25bi para a\u00e7\u00f5es brasileiras. Aloca\u00e7\u00e3o em emergentes em 5,3% vs m\u00e9dia de 6,7%. Projeta Selic em 11,50% fim 2026 com cortes de 3,5pp. Mant\u00e9m Ibovespa a 190k.","url":"https://valorinternational.globo.com/markets/news/2026/01/22/emerging-market-flows-could-bring-25bn-to-brazil-jp-morgan-says.ghtml"},
        {"date":"2026-02-04","bank":"Goldman Sachs","title":"Governo tem 'avers\u00e3o ao controle de gastos' \u2014 d\u00e9ficit fiscal volta acima de 8% do PIB","summary":"Alberto Ramos, economista-chefe do Goldman Sachs para Am\u00e9rica Latina, afirmou que o governo brasileiro tem 'avers\u00e3o ao controle de gastos' e que a 'postura fiscal pr\u00f3-c\u00edclica comprometeu severamente a credibilidade das metas fiscais'. O banco aponta que a fragilidade do arcabou\u00e7o fiscal dificultou a ancoragem das expectativas de infla\u00e7\u00e3o e elevou os pr\u00eamios de risco exigidos nos ativos dom\u00e9sticos. D\u00e9ficit nominal voltou a superar 8% do PIB, com d\u00edvida bruta projetada em 82,9% do PIB ao fim de 2026. Sem consolida\u00e7\u00e3o fiscal cr\u00edvel, o custo de financiamento do setor p\u00fablico tende a permanecer sob press\u00e3o.","url":"https://www.infomoney.com.br/economia/governo-brasileiro-tem-aversao-a-controlar-gastos-diz-goldman-sachs/"},
        {"date":"2026-02-02","bank":"BTG Pactual","title":"10SIM - Buscando bons m\u00faltiplos","summary":"BTG ajustou carteira em busca de m\u00faltiplos atraentes. Allos substitui Cyrela. Stone entra com 5% (P/L 6x, dividend yield 25%). Prio substitui Embraer. Nubank vai para 15%, Ita\u00fa reduz para 10%. Ibovespa com fortes fluxos estrangeiros.","url":"https://content.btgpactual.com/research/files/file/2026-02-02T083121.667_BTG%2010SIM%20FEV26.pdf"},
        {"date":"2026-03-26","bank":"Goldman Sachs","title":"A\u00e7\u00f5es brasileiras para liderar retomada","summary":"Goldman Sachs listou a\u00e7\u00f5es para liderar retomada de fluxo para emergentes. C\u00edclicas: BTG, B3, Nubank, Renner, SmartFit, Cyrela, GPS, C&A, Vibra. Defensivas: Copel, Equatorial, Sabesp, Multiplan, Rede D'Or. P/L de 13,3x para 2026, 15% abaixo m\u00e9dia hist\u00f3rica.","url":"https://www.infomoney.com.br/mercados/goldman-sachs-as-acoes-do-brasil-que-podem-liderar-retomada-de-fluxo-para-emergentes/"},
        {"date":"2026-04-22","bank":"BofA","title":"Elevou Ibovespa target para 210k","summary":"BofA elevou proje\u00e7\u00e3o do Ibovespa de 180k para 210k fim 2026. Mant\u00e9m overweight. Selic em 13,25% fim 2026, 12,50% em 2027. Projeta crescimento de lucros de 27% para empresas dom\u00e9sticas em 2026. Prefer\u00eancia por financeiros e utilities.","url":"https://www.bloomberglinea.com.br/mercados/bofa-eleva-projecao-para-o-ibovespa-e-mantem-recomendacao-de-compra-para-brasil/"},
        {"date":"2026-05-04","bank":"BTG Pactual","title":"10SIM - Reduzindo exposi\u00e7\u00e3o a bancos","summary":"BTG removeu Ita\u00fa da 10SIM. Totvs substitui Ita\u00fa (P/L 15x 2027, 25% de corre\u00e7\u00e3o). Nubank permanece como \u00fanico banco. 20% em geradoras de energia (Axia, Eneva). Exposi\u00e7\u00e3o a petr\u00f3leo (Petrobras 15%) e fluxo de caixa longo prazo (Localiza, Motiva).","url":"https://content.btgpactual.com/research/files/file/2026-05-04T090908.646_BTG%2010SIM%20MAI26.pdf"},
        {"date":"2026-05-09","bank":"Ita\u00fa BBA","title":"Reitera 185k mas condiciona a corte de juros","summary":"Ita\u00fa BBA mant\u00e9m proje\u00e7\u00e3o de 185k para 2026. Bull case: 253k, Bear case: 122k. Sem corte na Selic e \u00e2ncora fiscal cr\u00edvel, valoriza\u00e7\u00e3o pode n\u00e3o se concretizar. D\u00edvida bruta em 81,3% do PIB. Valuation atrativo \u00e9 o principal pilar.","url":"https://www.piranot.com.br/2026/05/09/noticias/economia/itau-bba-projeta-ibovespa-a-185-mil-pontos-em-2026-mas-condiciona-alta-a-corte-de-juros-e-ancora-fiscal/"},
        {"date":"2026-05-13","bank":"Morgan Stanley","title":"Projeta Ibovespa a 240k meados 2027","summary":"Morgan Stanley projeta Ibovespa em 240k meados 2027 (+33%). Reitera overweight. Brasil \u00e9 mercado favorito na AL. Potencial de US$25bi em fluxos. Projeta Selic 13% fim 2026, 10,5% fim 2027. Elei\u00e7\u00e3o de 2026 como catalisador.","url":"https://valorinveste.globo.com/mercados/renda-variavel/bolsas-e-indices/noticia/2026/05/13/morgan-stanley-v-ibovespa-perto-de-240-mil-pontos-e-potencial-de-us-25-bilhes-para-a-bolsa.ghtml"},
        {"date":"2026-06-01","bank":"BTG Pactual","title":"10SIM - Ita\u00fa substitui Nubank, Equatorial volta","summary":"BTG trouxe Ita\u00fa de volta (15%) substituindo Nubank. Equatorial substitui Allos. Ibovespa caiu 7,06% em maio, pior queda desde 2023. BTG enxerga valuation 'reconhecidamente baixo' e janela de oportunidade. Reduziu Petrobras e Localiza para 10%.","url":"https://exame.com/invest/mercados/btg-troca-nubank-por-itau-e-allos-por-equatorial-em-carteira-de-acoes-de-junho/"},
        {"date":"2026-06-12","bank":"BTG Pactual","title":"Rebaixa Brasil para neutro na Am\u00e9rica Latina \u2014 cen\u00e1rio menos previs\u00edvel","summary":"O BTG Pactual cortou a recomenda\u00e7\u00e3o para a\u00e7\u00f5es brasileiras de overweight para market perform (neutro) dentro da estrat\u00e9gia regional de Am\u00e9rica Latina. Motivo: cen\u00e1rio macroecon\u00f4mico menos previs\u00edvel, com perspectivas monet\u00e1rias e fiscais mais incertas. Apesar da corre\u00e7\u00e3o recente, o banco acredita que pode levar tempo at\u00e9 os pre\u00e7os ficarem mais atrativos ou haver maior clareza sobre o cen\u00e1rio. Brasil passa a dividir classifica\u00e7\u00e3o neutra com o Chile; Col\u00f4mbia promovida a overweight. Nota: call de estrat\u00e9gia macro regional \u2014 diferente da carteira 10SIM mensal.","url":"https://www.moneytimes.com.br/btg-pactual-reduz-recomendacao-para-bolsa-brasileira-para-neutra-lils/"},
        {"date":"2026-06-10","bank":"BofA","title":"Cortou Brasil para neutro - Selic a 14,25%","summary":"BofA rebaixou Brasil de overweight para marketweight (neutro). Revisou Selic para 14,25% fim 2026 (antes 13,25%). Apenas um corte adicional em junho seguido de pausa prolongada. Prefer\u00eancia por bancos resilientes. Equatorial substitui Copel.","url":"https://www.estadao.com.br/einvestidor/cenarios-e-mercado/bofa-corta-brasil-para-neutro-e-ve-selic-mais-alta-por-mais-tempo/"},
        {"date":"2026-06-16","bank":"Morgan Stanley","title":"Reitera overweight ap\u00f3s corre\u00e7\u00e3o","summary":"Morgan Stanley reitera overweight para Brasil ap\u00f3s corre\u00e7\u00e3o. Brasil negocia a 8,2x P/L, pr\u00f3ximo de cen\u00e1rios pessimistas. Assimetria positiva. Prefer\u00eancia por energia, materiais, utilities e financeiros. Elei\u00e7\u00f5es e trajet\u00f3ria fiscal como pontos de aten\u00e7\u00e3o.","url":"https://www.infomoney.com.br/mercados/mercado-brasileiro-ganha-com-ia-morgan-stanley-ve-ciclo-positivo-e-reitera-compra/"},
        {"date":"2025-07-09","bank":"Citi","title":"Brasil: 8,3x P/L forward, 1 desvio abaixo da m\u00e9dia hist\u00f3rica","summary":"Andre Mazini, head de research LATAM do Citi: Ibovespa a 8,3x P/L forward vs 12x Chile/M\u00e9xico, 13x China, 20+ EUA/UK. Empresas brasileiras entregando bom momentum de lucros e desalavancadas. Estrangeiros compraram R$24B em a\u00e7\u00f5es brasileiras em 2025. Brasil \u00e9 4% do MSCI EM, qualquer realoca\u00e7\u00e3o global move o ponteiro.","url":"https://www.citigroup.com/rcs/citigpa/storage/public/Reaseach_Citi_E41_TRANSCRIPT.pdf"},
        {"date":"2025-10-17","bank":"Citi","title":"Reduz risco na carteira MVP; eleva utilities e Petrobras","summary":"Citi reduziu beta da carteira MVP Brasil, citando incertezas pol\u00edticas e valuations inflados nos EUA. Elevou utilities de 15% para 35% e Petrobras de 5% para 10%. Excluiu MBRF, BB, C&A, Klabin e Fleury. Incluiu Cyrela, Nu Holdings, Localiza e Equatorial. Ibovespa ainda com valuation atrativo vs pares globais.","url":"https://www.moneytimes.com.br/citi-ve-mercados-instaveis-e-reduz-risco-em-carteira-de-acoes-do-brasil-jals/"},
        {"date":"2025-12-08","bank":"Citi","title":"Nubank e BTG s\u00e3o top picks para ciclo de corte de juros","summary":"Citi indicou Nubank e BTG Pactual como top picks no setor financeiro para 2026. Al\u00edvio na Selic pode ampliar demanda por cr\u00e9dito. Destaque para resili\u00eancia do Ita\u00fa. Elei\u00e7\u00e3o e pol\u00edtica econ\u00f4mica podem reprecificar o setor.","url":"https://einvestidor.estadao.com.br/ultimas/citi-top-picks-nubank-btg-pactual-juros-2026/"},
        {"date":"2025-12-19","bank":"Citi","title":"Investidor local deve puxar alta da bolsa em 2026; projeta 3pp de cortes","summary":"Citi prev\u00ea que investidor local ser\u00e1 principal alavanca da bolsa em 2026 com in\u00edcio do ciclo de cortes. Projeta 3pp de al\u00edvio na Selic. Aloca\u00e7\u00e3o em a\u00e7\u00f5es em 6% vs m\u00e9dia de 8,3% - revers\u00e3o pode gerar R$238B em fluxos. Recomenda Cyrela, CPFL, Neoenergia, Equatorial, Weg, Marcopolo, Smartfit, Vivara, Mercado Livre e GPA.","url":"https://exame.com/invest/mercados/investidor-local-deve-puxar-alta-da-bolsa-brasileira-em-2026-preve-citi/"},
        {"date":"2026-06-19","bank":"Citi","title":"Bancos mais cautelosos com juros altos; Ita\u00fa se destaca","summary":"Citi v\u00ea mudan\u00e7a para tom mais cauteloso nos bancos brasileiros. Maior seletividade no cr\u00e9dito favorece Ita\u00fa. BTG e BR Partners com ROE > 20%. BB preocupa no agroneg\u00f3cio por poss\u00edvel renegocia\u00e7\u00e3o de d\u00edvidas rurais. Inter mant\u00e9m ritmo s\u00f3lido de crescimento de ~30% ao ano.","url":"https://www.estadao.com.br/einvestidor/cenarios-e-mercado/citi-ve-bancos-mais-cautelosos-com-juros-altos-itau-se-destaca-e-bb-preocupa-no-agro/"},
        {"date":"2026-06-24","bank":"Citi","title":"Corta pre\u00e7o-alvo de bancos por deteriora\u00e7\u00e3o macro; Ita\u00fa e BTG preferidos","summary":"Citi reduziu pre\u00e7os-alvo de bancos brasileiros refletindo custo de capital mais elevado e juros altos por mais tempo. Ita\u00fa (R$54\u2192R$50) e BTG (R$74\u2192R$70) mantidos como compra. Bradesco (R$24\u2192R$20) compra. BB (R$25\u2192R$21) e Santander (R$36\u2192R$28) neutros. Aumento sist\u00eamico de ativos problem\u00e1ticos e provis\u00f5es.","url":"https://www.cnnbrasil.com.br/economia/negocios/citi-corta-preco-alvo-de-bancos-brasileiros-por-deterioracao-macroeconomica/"},
        {"date":"2026-06-24","bank":"Citi","title":"Bolsa brasileira ficou barata ap\u00f3s corre\u00e7\u00e3o; ponto de entrada atrativo","summary":"Andre Mazini (Citi): Ibovespa caiu de 200k para 170k, mercado a 8,3x P/L. 'Brasil ficou significativamente mais barato e o desconto para mercados desenvolvidos aumentou'. M\u00e9dia hist\u00f3rica \u00e9 10,5x. Recomenda\u00e7\u00e3o overweight dentro da regi\u00e3o. Otimismo especial com construtoras de baixa renda. 'Os melhores pontos de entrada surgem quando o sentimento est\u00e1 negativo'.","url":"https://valorinternational.globo.com/markets/news/2026/06/24/brazil-stocks-look-cheap-after-selloff-citi-says.ghtml"},
        {"date":"2026-06-26","bank":"JP Morgan","title":"Eleva BTG Pactual para compra; v\u00ea 30% de upside","summary":"JP Morgan elevou recomenda\u00e7\u00e3o de BTG Pactual (BPAC11) de Neutro para Overweight (compra). Pre\u00e7o-alvo revisado de R$61 para R$66 por unit ao fim de 2027, implicando potencial de alta de ~30%. JPMorgan v\u00ea BTG como 'vencedor em participa\u00e7\u00e3o de mercado' com hist\u00f3rico de crescimento consistente e resili\u00eancia em diferentes cen\u00e1rios macro. Valuation atrativo apesar da alta recente.","url":"https://www.moneytimes.com.br/btg-pactual-bpac11-jp-morgan-eleva-recomendacao-para-compra-e-ve-banco-como-vencedor-em-participacao-de-mercado-lmrs/"},
        {"date":"2026-06-27","bank":"Goldman Sachs","title":"Ibovespa a 8,6x P/L - janela de entrada antes de novo ciclo","summary":"Goldman Sachs mant\u00e9m overweight Brasil. Mercado negocia a 8,6x P/L 2026 em torno do m\u00ednimo hist\u00f3rico. Analistas v\u00eeem ponto de entrada assim\u00e9trico antes de eventual in\u00edcio de cortes do Copom. Prefer\u00eancia por financeiros (BTG, Nubank, Ita\u00fa), utilities e exportadoras de prote\u00edna. Selic projetada em 13,25% fim 2026.","url":"https://www.goldmansachs.com/insights/outlooks/2026-outlooks"},
        {"date":"2026-06-29","bank":"Morgan Stanley","title":"Reitera overweight; Ibovespa a 240k em 2027 com queda de juros","summary":"Morgan Stanley reitera overweight para a\u00e7\u00f5es brasileiras. Projeta Ibovespa em 240k pontos em meados de 2027 (+40%). Catalisador: ciclo de cortes da Selic a partir de ago/2026, meta terminal 10,5% em 2027. Brasil mercado favorito na AL. Setores: energia, materiais, utilities e financeiros.","url":"https://exame.com/invest/mercados/morgan-stanley-ve-ibovespa-aos-240-mil-pontos-mas-nao-este-ano/"},
        {"date":"2026-05-29","bank":"UBS","title":"UBS rebaixa Brasil de atrativo para neutro antes das elei\u00e7\u00f5es","summary":"UBS cortou recomenda\u00e7\u00e3o de atrativo para neutro citando elei\u00e7\u00e3o de outubro, ciclo de cortes da Selic mais curto e raso, e press\u00e3o fiscal pr\u00e9-eleitoral. Recomenda manter posi\u00e7\u00f5es sem adicionar exposi\u00e7\u00e3o.","url":"https://exame.com/invest/mercados/ubs-rebaixa-mercado-de-acoes-brasileiro-de-atrativo-para-neutro/"},
        {"date":"2026-07-01","bank":"XP Investimentos","title":"XP reduz alvo do Ibovespa para 200 mil pontos","summary":"XP cortou proje\u00e7\u00e3o de 205k para 200k pontos para fim de 2026. Revis\u00e3o reflete alta dos juros reais longos e sa\u00edda de R$ 8,8bi de estrangeiros em junho. Cen\u00e1rio otimista: 259k; pessimista: 158k.","url":"https://www.infomoney.com.br/mercados/xp-reduz-projecao-do-ibovespa-para-200-mil-pontos-mas-ve-2-motivos-para-otimismo/"},
        {"date":"2026-06-01","bank":"XP Investimentos","title":"Est\u00e1 na hora de comprar Bolsa brasileira","summary":"XP manteve target de 205k e declarou ser hora de comprar Brasil ap\u00f3s corre\u00e7\u00e3o de maio (-7%). Indicador t\u00e9cnico/sentimento voltou a territ\u00f3rio de compra, similar a janeiro/2025. Recomenda a\u00e7\u00f5es dom\u00e9sticas de qualidade.","url":"https://www.infomoney.com.br/mercados/esta-na-hora-de-comprar-bolsa-brasileira-diz-xp-que-ve-ibovespa-a-205-mil-em-2026/"},
        {"date":"2026-06-08","bank":"XP Investimentos","title":"XP eleva target para 205k e aponta 2 temas para o 2\u00ba semestre","summary":"XP elevou proje\u00e7\u00e3o para 205k pontos ao fim de 2026 (+21% vs. n\u00edvel de junho) e apontou 2 temas centrais: ciclo eleitoral e trajet\u00f3ria de juros/infla\u00e7\u00e3o. Recomenda compra para o 2\u00ba semestre.","url":"https://www.infomoney.com.br/mercados/xp-ve-ibovespa-a-205-mil-pontos-e-aponta-2-grandes-temas-para-acoes-no-2o-semestre/"},
        {"date":"2026-06-15","bank":"Goldman Sachs","title":"7 raz\u00f5es para comprar utilities ap\u00f3s queda de 16%","summary":"Goldman Sachs listou 7 raz\u00f5es para comprar utilities brasileiras ap\u00f3s setor cair ~16% desde abril. Dividend yield de 10-14% ao ano em 2026-28, M&A em energia/saneamento e efeito El Ni\u00f1o favor\u00e1vel. Preferidas: Sabesp, Copel, Equatorial.","url":"https://www.infomoney.com.br/mercados/goldman-sachs-lista-7-razoes-para-comprar-acoes-de-utilities-apesar-da-queda-na-bolsa/"},
        {"date":"2026-07-01","bank":"BTG Pactual","title":"10SIM julho: Rede D'Or entra, Mercado Livre sai","summary":"BTG lan\u00e7ou a 10SIM de julho com uma mudan\u00e7a: RDOR3 substitui MELI34. Rede D'Or avaliada como queda exagerada, cresce 15% ao ano a 14x P/L 2026. Carteira acumula +21,9% desde dez/2024 vs +15,4% do Ibovespa. Banco v\u00ea a\u00e7\u00f5es brasileiras baratas, mas juros longos precisam ceder para destravar valoriza\u00e7\u00e3o.","url":"https://exame.com/invest/onde-investir/btg-bpac11-retira-meli-de-carteira-recomendada-reduz-exposicao-em-varejo-e-aposta-em-rede-dor/"},
        {"date":"2026-07-01","bank":"Goldman Sachs","title":"Goldman reitera overweight; Ibovespa a 8x est\u00e1 barato","summary":"Goldman Sachs reiterou overweight para o Brasil dentro do portf\u00f3lio de emergentes. A\u00e7\u00f5es negociam a ~8x lucros projetados \u2014 patamar historicamente compat\u00edvel com in\u00edcio de ciclo de queda de juros. Prefere bancos defensivos, utilities, telecom, construtoras de baixa renda e varejistas descontados. Alvo de 215k pontos em 12 meses.","url":"https://www.infomoney.com.br/mercados/goldman-ve-acoes-brasileiras-baratas-e-reitera-compra-para-brasil-entre-emergentes/"},
        {"date":"2026-07-02","bank":"Goldman Sachs","title":"Brasil \u00e9 o preferido na Am\u00e9rica Latina; a\u00e7\u00f5es seguem baratas","summary":"Goldman Sachs reiterou em 02/jul que o Brasil continua sendo o mercado de a\u00e7\u00f5es preferido na Am\u00e9rica Latina dentro da carteira de emergentes. Com o Ibovespa em torno de 171k, as a\u00e7\u00f5es negociam a ~8x P/L forward \u2014 desconto hist\u00f3rico frente a mercados desenvolvidos (20x+). O banco destaca a assimetria positiva e mant\u00e9m overweight. Infla\u00e7\u00e3o, juros reais e elei\u00e7\u00f5es monitorados como riscos.","url":"https://br.investing.com/news/economy-news/goldman-sachs-ve-acoes-brasileiras-baratas-e-reitera-overweight-para-brasil-entre-mercados-emergentes-1989541"},
        {"date":"2026-06-29","bank":"Ita\u00fa BBA","title":"Ibovespa opera indefinido pr\u00f3ximo a suporte t\u00e9cnico de 167,6k","summary":"Relat\u00f3rio Daily Chartist do Ita\u00fa BBA (29/jun) apontou que o Ibovespa segue indefinido, operando pr\u00f3ximo a um importante n\u00edvel de suporte t\u00e9cnico em 167.600 pontos. Leitura t\u00e9cnica/neutra \u2014 sem revis\u00e3o de target fundamentalista, que segue em 185k para fim de 2026.","url":"https://www.infomoney.com.br/mercados/ibovespa-apos-1o-semestre-de-altos-e-baixos-o-que-esperar-para-o-indice-ate-o-fim-de-2026/"},
        {"date":"2026-07-01","bank":"Ita\u00fa BBA","title":"Carteira recomendada de a\u00e7\u00f5es: 80% de trocas para julho","summary":"Ita\u00fa BBA trocou 4 das 5 a\u00e7\u00f5es da carteira mensal. Entram Embraer (EMBJ3), Nubank (ROXO34), Sabesp (SBSP3) e Bradesco (BBDC4). Saem Aura Minerals (AURA33), BTG Pactual (BPAC11), Equatorial (EQTL3) e Petrobras (PETR4). Axia Energia (AXIA3) \u00e9 a \u00fanica que permanece. Carteira caiu 4,5% em junho, 3p.p. pior que o Ibovespa (-1%).","url":"https://www.moneytimes.com.br/itau-bba-troca-80-das-acoes-em-carteira-recomendada-para-julho-onde-investir-lmrs/"},
        {"date":"2026-07-01","bank":"BTG Pactual","title":"Small Caps julho: Banco Inter e Marcopolo entram na carteira","summary":"BTG Pactual promoveu duas trocas na carteira recomendada de small caps para julho: Banco Inter (INBR32) e Marcopolo (POMO4) entram, substituindo Banco Pine (PINE4) e SBF (SBFG3). Carteira mant\u00e9m Copasa, Sanepar, Smart Fit, 3tentos, Orizon, Tenda, Pague Menos e Bemobi, todas com peso de 10%. Foco em empresas com valor de mercado pr\u00f3ximo a R$15 bilh\u00f5es. Nota: carteira distinta da 10SIM mensal.","url":"https://www.seudinheiro.com/2026/bolsa-dolar/btg-pactual-troca-duas-acoes-em-carteira-de-small-caps-para-julho-veja-quem-entra-quem-sai-e-as-apostas-do-banco/"},
        {"date":"2026-07-01","bank":"XP Investimentos","title":"Carteira Top Dividendos Plus julho: eleva ITSA4 e PETR4, reduz PLPL3 e POMO4","summary":"XP ajustou pesos na Carteira Top Dividendos Plus para julho/2026: ITSA4 e PETR4 subiram de 10% para 15% cada; PLPL3 e POMO4 ca\u00edram de 10% para 5% cada. Carteira quantitativa focada em boas pagadoras de dividendos com recorr\u00eancia.","url":"https://conteudos.xpi.com.br/acoes/carteiras/carteira-top-dividendos-plus-julho-2026/"},
        {"date":"2026-07-01","bank":"Santander","title":"Carteira de a\u00e7\u00f5es julho: Sabesp entra, RD Sa\u00fade sai","summary":"Santander incluiu Sabesp (SBSP3) e retirou RD Sa\u00fade (RADL3) da carteira recomendada de a\u00e7\u00f5es para julho/2026. Carteira de dividendos do banco n\u00e3o teve trocas no m\u00eas (mant\u00e9m ALOS3, AXIA6, BPAC11, CPLE3, VIVT3, VALE3, VBBR3, CURY3, ITUB4, PETR3), acumulando +12,88% em 2026 vs +7,04% do Ibovespa.","url":"https://euqueroinvestir.com/acoes/carteira-de-acoes-para-julho-santander-traz-novidade"},
        {"date":"2026-07-01","bank":"BB Investimentos","title":"Carteira 5+ troca todas as a\u00e7\u00f5es ap\u00f3s queda de 6,44% em junho","summary":"BB Investimentos reformulou 100% da Carteira 5+ para julho/2026. Entram Allos (ALOS3), Bradesco (BBDC4), Cemig (CMIG4), Motiva (MOTV3) e Vivara (VIVA3), 20% cada. Saem Bradespar, C&A, CSN, Cury e Lojas Renner. Carteira anterior caiu 6,44% em junho, abaixo do Ibovespa (-1,01% no per\u00edodo).","url":"https://bpmoney.com.br/mercado/bb-investimentos-troca-todas-acoes-carteira/"},
        {"date":"2026-07-10","bank":"Mercado","title":"IPCA surpreende para baixo; Ibovespa sobe a maior valor em 2 meses","summary":"IPCA de junho veio a 0,16%, abaixo da mediana de mercado (~0,31%), levando a infla\u00e7\u00e3o acumulada em 12 meses a 4,64% (ante 4,72%). Ibovespa fechou em alta de 2,86% em 10/jul, aos 177.680 pontos \u2014 maior patamar desde 14/mai e terceira semana consecutiva de ganhos (+2,18% na semana). Mercado passou a precificar maior chance de corte de 0,25p.p. na Selic j\u00e1 na reuni\u00e3o do Copom de 4-5/ago. Bancos lideraram a alta (BPAC11 +5,48%, BBAS3 +2,90%).","url":"https://www.infomoney.com.br/mercados/ibovespa-hoje-bolsa-de-valores-ao-vivo-10072026/"},
        {"date":"2026-07-10","bank":"Goldman Sachs","title":"13 a\u00e7\u00f5es preferidas e 5 preteridas para aproveitar a corre\u00e7\u00e3o da Bolsa","summary":"Goldman Sachs recomenda aproveitar a queda de 17% do MSCI Brazil desde as m\u00e1ximas de abril/2026 (tese de revers\u00e3o \u00e0 m\u00e9dia), citando ambiente incerto: Fed mais restritivo, baixa exposi\u00e7\u00e3o do Brasil a IA, elei\u00e7\u00f5es presidenciais. 13 preferidas (compra): Petrobras (valuation 4x lucro, alto dividend yield), Ita\u00fa Unibanco (maior ROE do setor, 25,4% em 2026), BTG Pactual, Nubank (EPS +41% 2025-28), Cyrela, Bradsa\u00fade (caixa l\u00edquido R$8bi), GPS, Lojas Renner, Smartfit, Vibra, Direcional, Rede D'Or, Sabesp (TIR real 10%). 5 preteridas (venda): Banco do Brasil (inadimpl\u00eancia subindo, ROE abaixo do custo de capital), CSN, CSN Minera\u00e7\u00e3o (vis\u00e3o baixista min\u00e9rio de ferro), Engie Brasil, Telef\u00f4nica Brasil.","url":"https://www.infomoney.com.br/onde-investir/goldman-aponta-13-acoes-preferidas-e-5-preteridas-para-aproveitar-a-queda-da-bolsa/"},
        {"date":"2026-07-16","bank":"Mercado","title":"Novo tarifa\u00e7o dos EUA sobre o Brasil derruba Ibovespa","summary":"USTR anunciou na noite de 15/07 taxa\u00e7\u00e3o adicional de 25% sobre produtos brasileiros a partir de 22/07, ap\u00f3s investiga\u00e7\u00e3o Section 301 sobre pr\u00e1ticas comerciais do pa\u00eds. Ibovespa abriu em forte queda em 16/07, chegando a cair mais de 2.000 pontos (-1,11%, 174.056 pts \u00e0s 10h53). D\u00f3lar subiu 0,38% a R$5,0975. Produtos afetados: a\u00e7\u00facar, m\u00e1quinas agr\u00edcolas, vestu\u00e1rio, m\u00e1quinas el\u00e9tricas, papel e a\u00e7o. Isentos: caf\u00e9, carne bovina, terras raras, energia, aeronaves e pe\u00e7as.","url":"https://www.moneytimes.com.br/ibovespa-futuro-16-7-26-apsa/"},
        {"date":"2026-07-14","bank":"Morgan Stanley","title":"Refor\u00e7a aposta no Brasil \u2014 S\u00e3o Martinho entra, Axia \u00e9 maior convic\u00e7\u00e3o","summary":"Morgan Stanley refor\u00e7ou a aposta no Brasil como mercado favorito na Am\u00e9rica Latina, citando pessimismo elevado dos investidores locais como gatilho para recupera\u00e7\u00e3o de fluxos. S\u00e3o Martinho (SMTO3) entrou na carteira apostando na alta dos pre\u00e7os do a\u00e7\u00facar em contexto de El Ni\u00f1o. Axia Energia (AXIA3) teve a posi\u00e7\u00e3o aumentada, descrita como a aposta de maior convic\u00e7\u00e3o do banco no Brasil, beneficiada por pre\u00e7os de energia em alta. Suzano (SUZB3) tamb\u00e9m teve exposi\u00e7\u00e3o refor\u00e7ada. Copel (CPLE6) teve posi\u00e7\u00e3o parcialmente reduzida por risco de chuvas intensas no Sul pressionarem pre\u00e7os de energia.","url":"https://bpmoney.com.br/mercado/morgan-stanley-reforca-aposta-no-brasil-veja-acoes-favoritas-para-julho/"},
        {"date":"2026-07-20","bank":"Citi","title":"3 motivos para comprar Brasil em meio ao caos global","summary":"Citi listou 3 motivos para comprar a\u00e7\u00f5es brasileiras em meio \u00e0 turbul\u00eancia global: (1) menor exposi\u00e7\u00e3o da economia brasileira a atividades ligadas a IA vs. outros mercados; (2) dist\u00e2ncia geogr\u00e1fica dos principais focos de tens\u00e3o geopol\u00edtica; (3) resili\u00eancia das exporta\u00e7\u00f5es brasileiras apesar da escalada protecionista dos EUA (tarifa\u00e7o). Carteira com 10% cada em Petrobras (PETR4), Multiplan (MULT3), Cury (CURY3), Embraer (EMBR3), Equatorial (EQTL3) e RD Sa\u00fade (RADL3); 5% cada em Ita\u00fa Unibanco (ITUB4), Caixa Seguridade (CXSE3), Prio (PRIO3), Axia (AXIA3), Smart Fit (SMFT3) e Vivara (VIVA3).","url":"https://www.seudinheiro.com/2026/bolsa-dolar/citi-lista-3-motivos-para-comprar-brasil-em-meio-ao-caos-global-e-estas-sao-as-acoes-escolhidas-pelo-banco-bdap/"}
    ]
    bank_filter = request.args.get('bank')
    if bank_filter:
        calls = [c for c in calls if c['bank'] == bank_filter]
    return jsonify(calls)

@app.route('/api/banks')
def get_banks():
    banks = [
        {"name": "BTG Pactual", "color": "#5c6bc0"},
        {"name": "Ita\u00fa BBA", "color": "#ff8f00"},
        {"name": "Morgan Stanley", "color": "#00bfa5"},
        {"name": "BofA", "color": "#ef5350"},
        {"name": "Goldman Sachs", "color": "#fdd835"},
        {"name": "JP Morgan", "color": "#42a5f5"},
        {"name": "Citi", "color": "#9c27b0"},
        {"name": "XP Investimentos", "color": "#26c6da"},
        {"name": "UBS", "color": "#e53935"},
        {"name": "Santander", "color": "#c62828"},
        {"name": "BB Investimentos", "color": "#0d47a1"}
    ]
    return jsonify(banks)


TICKER_NAMES = {
    "PETR4": "Petrobras", "VALE3": "Vale", "WEGE3": "WEG", "RENT3": "Localiza",
    "MGLU3": "Magazine Luiza", "B3SA3": "B3", "EQTL3": "Equatorial Energia",
    "BPAC11": "BTG Pactual", "ITUB4": "Itaú Unibanco", "BBDC4": "Bradesco",
    "BBAS3": "Banco do Brasil", "SANB11": "Santander Brasil", "CXSE3": "Caixa Seguridade",
    "SUZB3": "Suzano", "RDOR3": "Rede D'Or", "LREN3": "Lojas Renner",
    "BBSE3": "BB Seguridade", "PRIO3": "Prio", "GGBR4": "Gerdau",
    "ABEV3": "Ambev", "ASAI3": "Assaí Atacadista",
    "EMBJ3": "Embraer", "RAIL3": "Rumo", "TOTS3": "Totvs",
    "VIVT3": "Telefônica Brasil (Vivo)", "USIM5": "Usiminas",
    "CSNA3": "CSN", "MULT3": "Multiplan",
}


@app.route('/api/stock-calls')
def get_stock_calls():
    calls = [
        {"ticker": "PETR4", "bank": "BTG Pactual", "date": "2026-05-04", "action": "eleva alvo", "target": "US$ 25 (ADR)", "prior_target": "US$ 22,03 (ADR)", "view": "BULL", "title": "BTG eleva ADR da Petrobras para US$ 25", "summary": "BTG Pactual elevou o preço-alvo do ADR da Petrobras (PBR) de US$ 22,03 para US$ 25, citando trimestre forte e dividendos robustos esperados. Mantém recomendação de compra.", "url": "https://www.seudinheiro.com/2026/empresas/petrobras-petr4-deve-entregar-trimestre-forte-e-dividendos-robustos-diz-btg-preco-alvo-do-adr-sobe-para-us-25-lvgb/"},
        {"ticker": "PETR4", "bank": "BofA", "date": "2026-06-19", "action": "corta alvo", "target": "R$ 55 / US$ 22 (ADR)", "prior_target": "R$ 65 / US$ 24,80 (ADR)", "view": "BULL", "title": "BofA corta alvo de Petrobras após queda do petróleo", "summary": "BofA cortou o preço-alvo de PETR4 de R$ 65 para R$ 55 (-15%) e do ADR de US$ 24,80 para US$ 22 (-11%), acompanhando corte também em Prio, após a queda do petróleo no período. Manteve recomendação de compra. Data aproximada (período de queda do petróleo pós-acordo EUA-Irã, jun/2026 — ajustada para sexta-feira 19/jun, dia útil mais próximo).", "url": "https://www.seudinheiro.com/2026/empresas/petrobras-petr4-prio-prio3-e-mais-bofa-corta-precos-alvo-apos-queda-do-petroleo-lvgb/"},
        {"ticker": "VALE3", "bank": "JP Morgan", "date": "2026-05-22", "action": "eleva alvo", "target": "R$ 104", "prior_target": "R$ 99", "view": "BULL", "title": "JP Morgan eleva alvo da Vale, vê ação descontada", "summary": "JP Morgan elevou o preço-alvo de VALE3 de R$ 99 para R$ 104, mantendo overweight (compra). Driver principal: segmento de metais básicos (cobre e níquel), com a divisão revisada para US$ 5,1 bi (+57% vs. estimativa anterior).", "url": "https://www.seudinheiro.com/2026/empresas/jp-morgan-ve-vale-vale3-descontada-demais-e-eleva-preco-alvo-lvgb/"},
        {"ticker": "VALE3", "bank": "Safra", "date": "2026-06-15", "action": "eleva alvo", "target": "R$ 86", "prior_target": None, "view": "NEUTRAL", "title": "Safra eleva alvo da Vale mas rebaixa para neutro", "summary": "Safra elevou o preço-alvo de VALE3 para R$ 86 por ação, mas rebaixou a recomendação para neutro após a forte alta do papel no período. Data aproximada (mesma janela do rali de metais básicos, jun/2026).", "url": "https://oespecialista.safra.com.br/analise/vale-vale3-safra-eleva-preco-alvo/"},
        {"ticker": "WEGE3", "bank": "Safra", "date": "2026-05-07", "action": "corta alvo", "target": "R$ 53", "prior_target": "R$ 57,40", "view": "NEUTRAL", "title": "Safra corta alvo da WEG após 1T26 fraco", "summary": "Safra reduziu o preço-alvo de WEGE3 de R$ 57,40 para R$ 53 (potencial de 19%) e rebaixou para neutro, após resultados fracos do 1T26 — câmbio desfavorável, demanda doméstica fraca e pressão de margem. Lucro líquido 2026 revisado -10,7% para R$ 6,089 bi.", "url": "https://www.moneytimes.com.br/weg-wege3-safra-e-bba-cortam-preco-alvo-apos-balanco-do-1t26-veja-projecoes-jvka/"},
        {"ticker": "WEGE3", "bank": "Itaú BBA", "date": "2026-05-07", "action": "corta alvo", "target": "R$ 48", "prior_target": "R$ 50", "view": "BULL", "title": "Itaú BBA corta alvo da WEG mas mantém compra", "summary": "Itaú BBA reduziu o preço-alvo de WEGE3 de R$ 50 para R$ 48 após o 1T26 fraco, mas manteve recomendação de compra. Lucro líquido 2026 revisado de R$ 6,6 bi para R$ 6 bi.", "url": "https://www.moneytimes.com.br/weg-wege3-safra-e-bba-cortam-preco-alvo-apos-balanco-do-1t26-veja-projecoes-jvka/"},
        {"ticker": "RENT3", "bank": "Citi", "date": "2026-05-08", "action": "corta alvo", "target": "R$ 54", "prior_target": "R$ 55", "view": "BULL", "title": "Citi corta levemente alvo da Localiza após 1T26", "summary": "Citi cortou o preço-alvo de RENT3 de R$ 55 para R$ 54 após o 1T26 — frota encerrou o trimestre menor, e o banco espera sazonalidade fraca e mix mais premium no 2T. Manteve compra: seminovos com desempenho sólido e ciclo de depreciação virtuoso. Data aproximada (janela de resultados do 1T26).", "url": "https://www.moneytimes.com.br/localiza-rent3-citi-corta-preco-alvo-apos-1t26-e-hora-de-comprar-ou-vender/"},
        {"ticker": "MGLU3", "bank": "BB Investimentos", "date": "2026-03-13", "action": "corta alvo", "target": "R$ 9,60", "prior_target": "R$ 9,80", "view": "NEUTRAL", "title": "BB-BI revisa levemente pra baixo alvo do Magalu", "summary": "BB Investimentos revisou o preço-alvo de MGLU3 de R$ 9,80 para R$ 9,60 ao fim de 2026, mantendo recomendação neutra. Data aproximada (mês de março/2026, conforme referência da publicação — ajustada para sexta-feira 13/mar, dia útil mais próximo).", "url": "https://investalk.bb.com.br/noticias/mercado/magazine-luiza-mglu3-revisao-preco-marco-26"},
        {"ticker": "B3SA3", "bank": "Citi", "date": "2026-04-09", "action": "eleva alvo", "target": "R$ 23", "prior_target": "R$ 19", "view": "BULL", "title": "Citi eleva B3 para compra e sobe alvo a R$ 23", "summary": "Citi elevou o preço-alvo de B3SA3 de R$ 19 para R$ 23 e mudou a recomendação de neutra para compra (+20% de potencial vs. fechamento de 09/abr). Suportado por revisão de lucro +17% (2026) e +13% (2027) após decisão do STJ sobre dedução de JCP, permitindo maior distribuição.", "url": "https://www.seudinheiro.com/2026/bolsa-dolar/b3-b3sa3-deve-distribuir-r-63-bilhoes-em-proventos-neste-ano-segundo-o-citi-banco-eleva-recomendacao-e-preco-alvo-lvgb/"},
        {"ticker": "EQTL3", "bank": "Itaú BBA", "date": "2026-05-15", "action": "eleva alvo", "target": "R$ 53,30", "prior_target": "R$ 48,70", "view": "BULL", "title": "Itaú BBA eleva alvo da Equatorial e elege top pick do setor", "summary": "Itaú BBA elevou o preço-alvo de EQTL3 de R$ 48,70 para R$ 53,30 (potencial de 40,2%), citando melhora no balanço e perfil de alavancagem, com espaço adicional pra investimentos orgânicos em distribuição. Mantém compra. Data aproximada (relatório publicado em maio/2026).", "url": "https://www.moneytimes.com.br/para-itau-bba-equatorial-eqtl3-esta-mal-precificada-lils/"},
        {"ticker": "BPAC11", "bank": "JP Morgan", "date": "2026-06-26", "action": "eleva alvo", "target": "R$ 66", "prior_target": "R$ 61", "view": "BULL", "title": "JP Morgan eleva BTG Pactual para compra; vê 30% de upside", "summary": "JP Morgan elevou BPAC11 de neutro para overweight (compra), com preço-alvo revisado de R$ 61 para R$ 66 por unit (fim de 2027), implicando ~30% de potencial de alta. Banco vê o BTG como 'vencedor em participação de mercado'.", "url": "https://www.moneytimes.com.br/btg-pactual-bpac11-jp-morgan-eleva-recomendacao-para-compra-e-ve-banco-como-vencedor-em-participacao-de-mercado-lmrs/"},
        {"ticker": "BPAC11", "bank": "Goldman Sachs", "date": "2026-01-13", "action": "reitera", "target": "R$ 63", "prior_target": None, "view": "BULL", "title": "Goldman lista BTG entre preferidas para bancos em 2026", "summary": "Goldman Sachs listou BTG Pactual como uma das ações preferidas do setor bancário brasileiro para 2026, com preço-alvo de R$ 63. Banco projeta crescimento de crédito de 9,5% em 2026 para o setor.", "url": "https://www.infomoney.com.br/mercados/goldman-sachs-projeta-2026-solido-para-bancos-brasileiros-e-destaca-acoes-preferidas/"},
        {"ticker": "ITUB4", "bank": "Citi", "date": "2026-06-24", "action": "corta alvo", "target": "R$ 50", "prior_target": "R$ 54", "view": "BULL", "title": "Citi corta alvo de Itaú mas mantém entre preferidas", "summary": "Citi reduziu o preço-alvo de ITUB4 de R$ 54 para R$ 50, refletindo custo de capital mais elevado e juros altos por mais tempo, mas manteve compra — Itaú segue preferido do banco no setor.", "url": "https://www.cnnbrasil.com.br/economia/negocios/citi-corta-preco-alvo-de-bancos-brasileiros-por-deterioracao-macroeconomica/"},
        {"ticker": "BBDC4", "bank": "Citi", "date": "2026-06-24", "action": "corta alvo", "target": "R$ 20", "prior_target": "R$ 24", "view": "BULL", "title": "Citi corta alvo do Bradesco, mantém compra", "summary": "Citi reduziu o preço-alvo de BBDC4 de R$ 24 para R$ 20, refletindo deterioração macroeconômica e aumento sistêmico de ativos problemáticos no setor, mas manteve recomendação de compra.", "url": "https://www.cnnbrasil.com.br/economia/negocios/citi-corta-preco-alvo-de-bancos-brasileiros-por-deterioracao-macroeconomica/"},
        {"ticker": "BBAS3", "bank": "Citi", "date": "2026-06-24", "action": "corta alvo", "target": "R$ 21", "prior_target": "R$ 25", "view": "NEUTRAL", "title": "Citi corta alvo do Banco do Brasil pra neutro", "summary": "Citi reduziu o preço-alvo de BBAS3 de R$ 25 para R$ 21, recomendação neutra, preocupado com possível renegociação de dívidas rurais no agronegócio.", "url": "https://www.cnnbrasil.com.br/economia/negocios/citi-corta-preco-alvo-de-bancos-brasileiros-por-deterioracao-macroeconomica/"},
        {"ticker": "BBAS3", "bank": "Goldman Sachs", "date": "2026-04-29", "action": "rebaixa venda", "target": "R$ 21", "prior_target": "R$ 24", "view": "BEAR", "title": "Goldman rebaixa Banco do Brasil para venda", "summary": "Goldman Sachs rebaixou BBAS3 de neutro para venda e reduziu o preço-alvo de R$ 24 para R$ 21. Maior preocupação: carteira rural, com inadimplência subindo nas linhas de custeio — projeta R$ 64 bi em provisões em 2026, acima do teto do guidance do próprio banco. Lucro 2026 projetado em R$ 21 bi (~6% abaixo do piso do guidance).", "url": "https://guiadoinvestidor.com.br/mercado/goldman-vira-a-mao-no-banco-do-brasil-bbas3-e-recomendacao-de-venda-derruba-acao/"},
        {"ticker": "SANB11", "bank": "Citi", "date": "2026-06-24", "action": "corta alvo", "target": "R$ 28", "prior_target": "R$ 36", "view": "NEUTRAL", "title": "Citi corta forte o alvo do Santander Brasil", "summary": "Citi reduziu o preço-alvo de SANB11 de R$ 36 para R$ 28 (o maior corte entre os bancos revisados nesse relatório), recomendação neutra.", "url": "https://www.cnnbrasil.com.br/economia/negocios/citi-corta-preco-alvo-de-bancos-brasileiros-por-deterioracao-macroeconomica/"},
        {"ticker": "CXSE3", "bank": "JP Morgan", "date": "2026-07-24", "action": "rebaixa venda", "target": "R$ 22", "prior_target": None, "view": "BEAR", "title": "JP Morgan rebaixa Caixa Seguridade para venda", "summary": "JP Morgan rebaixou CXSE3 de neutro para underweight (venda) após forte alta desde junho (+35% no acumulado de 2026). Preço-alvo de R$ 22 (dez/2027), próximo da cotação da época — upside próximo de zero. Ação caiu 5,21% no dia da rebaixa. Banco passou a preferir IRB e Porto Seguro no setor.", "url": "https://www.infomoney.com.br/mercados/jpmorgan-rebaixa-caixa-seguridade-e-prefere-irb-e-porto-no-setor-de-seguros-desempenho-acoes/"},
        {"ticker": "PRIO3", "bank": "BofA", "date": "2026-06-19", "action": "corta alvo", "target": "R$ 71", "prior_target": "R$ 82", "view": "BULL", "title": "BofA corta alvo de Prio após queda do petróleo", "summary": "BofA cortou o preço-alvo de PRIO3 de R$ 82 para R$ 71, no mesmo relatório em que cortou Petrobras, acompanhando a queda do petróleo no período. Manteve recomendação de compra. Data aproximada (mesmo relatório do corte de PETR4, jun/2026 — ajustada para sexta-feira 19/jun).", "url": "https://www.seudinheiro.com/2026/empresas/petrobras-petr4-prio-prio3-e-mais-bofa-corta-precos-alvo-apos-queda-do-petroleo-lvgb/"},
        {"ticker": "PRIO3", "bank": "Citi", "date": "2026-07-17", "action": "corta alvo", "target": "R$ 66", "prior_target": "R$ 77,50", "view": "BULL", "title": "Citi corta alvo de Prio mas mantém compra", "summary": "Citi reduziu o preço-alvo de PRIO3 de R$ 77,50 para R$ 66, mesmo esperando um trimestre historicamente forte para a empresa. Manteve recomendação de compra.", "url": "https://euqueroinvestir.com/acoes/prio-deve-ter-trimestre-historico-mas-citi-reduz-preco-alvo"},
        {"ticker": "SUZB3", "bank": "BofA", "date": "2026-04-07", "action": "corta alvo", "target": "R$ 57", "prior_target": "R$ 82", "view": "NEUTRAL", "title": "BofA corta forte o alvo da Suzano e rebaixa pra neutro", "summary": "BofA cortou o preço-alvo de SUZB3 de R$ 82 para R$ 57 e rebaixou a recomendação de compra para neutro, refletindo visão mais cautelosa sobre o mercado global de celulose — preços pressionados por mais tempo devido a excesso de oferta estrutural.", "url": "https://www.seudinheiro.com/2026/empresas/suzano-suzb3-bofa-corta-r-25-do-preco-alvo-e-acoes-despencam-lvgb/"},
        {"ticker": "RDOR3", "bank": "Bradesco BBI", "date": "2026-05-20", "action": "corta alvo", "target": "R$ 42", "prior_target": "R$ 44", "view": "BULL", "title": "Bradesco BBI corta projeções da Rede D'Or mas mantém compra", "summary": "Bradesco BBI reduziu o preço-alvo de RDOR3 de R$ 44 para R$ 42 (fim de 2026) após o resultado do 1T26, cortando a estimativa de lucro líquido ajustado em 8% para 2026 e 6% para 2027. Mesmo assim, o novo alvo ainda indica ~23% de potencial de alta. Manteve recomendação de compra.", "url": "https://www.seudinheiro.com/2026/empresas/rede-dor-rdor3-perdeu-forca-bradesco-bbi-corta-projecoes-mas-revela-por-que-tese-ainda-segue-atrativa-miql/"},
        {"ticker": "LREN3", "bank": "Safra", "date": "2026-03-12", "action": "eleva alvo", "target": "R$ 22", "prior_target": "R$ 21", "view": "BULL", "title": "Safra e BB elevam alvo da Lojas Renner de olho no 4T25", "summary": "Safra elevou o preço-alvo de LREN3 de R$ 21 para R$ 22 (potencial de 40%), de olho em bons fundamentos e nos números do 4T25. Mantém recomendação de compra.", "url": "https://www.seudinheiro.com/2026/empresas/safra-e-bb-investimentos-elevam-preco-alvo-de-lojas-renner-lren3-de-olho-em-bons-fundamentos-e-numeros-do-4t25-e-hora-de-comprar-kaes/"},
        {"ticker": "LREN3", "bank": "BB Investimentos", "date": "2026-03-12", "action": "eleva alvo", "target": "R$ 21,20", "prior_target": "R$ 19", "view": "BULL", "title": "BB Investimentos eleva alvo da Lojas Renner", "summary": "BB Investimentos elevou o preço-alvo de LREN3 de R$ 19 para R$ 21,20 (potencial de 35%), no mesmo movimento do Safra, citando bons fundamentos e resultados do 4T25. Mantém recomendação de compra.", "url": "https://www.seudinheiro.com/2026/empresas/safra-e-bb-investimentos-elevam-preco-alvo-de-lojas-renner-lren3-de-olho-em-bons-fundamentos-e-numeros-do-4t25-e-hora-de-comprar-kaes/"},
        {"ticker": "BBSE3", "bank": "Safra", "date": "2026-01-08", "action": "rebaixa venda", "target": "R$ 39", "prior_target": "R$ 47", "view": "BEAR", "title": "Safra rebaixa BB Seguridade pra venda e corta alvo", "summary": "Safra rebaixou BBSE3 de compra para venda e cortou o preço-alvo de R$ 47 para R$ 39, citando expectativa de crescimento zero no lucro por ação entre 2025-2028, refletindo dificuldades nos segmentos de seguros rurais e previdência.", "url": "https://www.seudinheiro.com/2026/empresas/hora-de-vender-bb-seguridade-bbse3-safra-faz-alertas-para-dividendos-e-tira-r-8-do-preco-alvo-por-que-tanto-pessimismo-lvgb/"},
        {"ticker": "GGBR4", "bank": "Citi", "date": "2026-07-13", "action": "eleva alvo", "target": "R$ 29", "prior_target": "R$ 27", "view": "BULL", "title": "Citi eleva alvo da Gerdau", "summary": "Citi elevou o preço-alvo de GGBR4 de R$ 27 para R$ 29, mantendo recomendação de compra.", "url": "https://www.seudinheiro.com/2026/economia/gerdau-ggbr4-citi-siderurgica-pode-surpreender-no-desempenho-trimestral-mlem/"},
        {"ticker": "GGBR4", "bank": "Itaú BBA", "date": "2026-04-01", "action": "eleva compra", "target": "R$ 24", "prior_target": None, "view": "BULL", "title": "Itaú BBA eleva Gerdau pra compra após queda de 10%", "summary": "Itaú BBA elevou a recomendação de GGBR4 de neutro para outperform (compra), mantendo o preço-alvo de R$ 24 pra fim de 2026. Justificativa: a queda de 10% do papel desde fevereiro criou uma oportunidade mais atraente de entrada.", "url": "https://www.infomoney.com.br/mercados/gerdau-ggbr4-itau-bba-ve-melhor-relacao-risco-retorno-e-eleva-compra-desempenho-acoes/"},
        {"ticker": "ABEV3", "bank": "Santander", "date": "2026-05-12", "action": "eleva alvo", "target": "R$ 16,50", "prior_target": "R$ 14,20", "view": "BULL", "title": "Santander eleva alvo da Ambev", "summary": "Santander elevou o preço-alvo de ABEV3 de R$ 14,20 para R$ 16,50 (fim de 2026), embora a recente valorização das ações já incorpore boa parte das perspectivas positivas para os próximos trimestres.", "url": "https://www.suno.com.br/noticias/ambev-abev3-santander-eleva-recomendacao-alvo-gss/"},
        {"ticker": "ASAI3", "bank": "BB Investimentos", "date": "2026-02-11", "action": "mantém alvo", "target": "R$ 14", "prior_target": None, "view": "BULL", "title": "BB Investimentos mantém alvo do Assaí após 4T25", "summary": "BB Investimentos manteve o preço-alvo de ASAI3 em R$ 14 (sem alteração) após analisar o resultado do 4T25, mantendo recomendação de compra. Resultado mostrou crescimento tímido de receita mas ganho de market share e melhora de margem. Data aproximada (fevereiro/2026, conforme referência da publicação).", "url": "https://investalk.bb.com.br/noticias/mercado/assai-asai3-revisao-preco-fev26"},
        {"ticker": "EMBJ3", "bank": "JP Morgan", "date": "2026-03-10", "action": "eleva alvo", "target": "R$ 109 (B3) / US$ 84 (ADR)", "prior_target": "R$ 108 (B3) / US$ 80 (ADR)", "view": "BULL", "title": "JP Morgan eleva alvo da Embraer, vê potencial de 30%", "summary": "JP Morgan elevou o preço-alvo de EMBJ3 de R$ 108 para R$ 109 (e do ADR de US$ 80 para US$ 84), mantendo overweight (compra), com potencial de valorização de ~30%. Nota: a Embraer trocou seu ticker de EMBR3 para EMBJ3 em novembro/2025 (e o ADR de ERJ para EMBJ na NYSE); é o mesmo papel.", "url": "https://www.seudinheiro.com/2026/empresas/embraer-embj3-jp-morgan-eleva-preco-alvo-e-calcula-potencial-de-alta-de-30-veja-os-catalisadores-para-a-acao-lvgb/"},
        {"ticker": "RAIL3", "bank": "JP Morgan", "date": "2026-02-23", "action": "corta alvo", "target": "R$ 19,50", "prior_target": "R$ 20", "view": "NEUTRAL", "title": "JP Morgan corta levemente alvo da Rumo", "summary": "JP Morgan reduziu o preço-alvo de RAIL3 de R$ 20 para R$ 19,50 (dez/2026), mantendo recomendação neutra — banco havia retomado cobertura do papel em janeiro/2026 após queda de 13% da ação em 2025 (vs. alta de 34% do Ibovespa no período).", "url": "https://www.infomoney.com.br/mercados/rumo-rail3-jpmorgan-reinicia-cobertura-apos-queda-de-13-das-acoes-veja-cenario/"},
        {"ticker": "TOTS3", "bank": "Itaú BBA", "date": "2026-06-30", "action": "corta alvo", "target": "R$ 46", "prior_target": "R$ 60", "view": "BULL", "title": "Itaú BBA corta forte o alvo da Totvs mas mantém compra", "summary": "Itaú BBA reduziu o preço-alvo de TOTS3 de R$ 60 para R$ 46, mas manteve recomendação de compra — mesmo com o corte, o banco vê potencial de valorização de 61,4%, considerando que a avaliação atual do mercado incorpora premissas conservadoras demais para o longo prazo.", "url": "https://www.moneytimes.com.br/totvs-tots3-itau-bba-passa-a-tesoura-no-preco-alvo-mas-ainda-ve-potencial-de-61-para-acao-apsa/"},
        {"ticker": "VIVT3", "bank": "UBS", "date": "2026-03-11", "action": "rebaixa venda", "target": "R$ 36", "prior_target": None, "view": "BEAR", "title": "UBS rebaixa Telefônica Brasil de compra pra venda", "summary": "UBS fez um rebaixamento duplo (double downgrade) de VIVT3, de compra direto para venda, com preço-alvo de R$ 36 (abaixo dos ~R$ 41 de fechamento). Banco projeta crescimento de fluxo de caixa livre de só 5% ao ano entre 2025-2027 (vs. ~12% dos pares regionais) e dividend yield perto de 7%, abaixo do patamar histórico de dois dígitos.", "url": "https://www.seudinheiro.com/2026/bolsa-dolar/dividendos-da-telefonica-vivt3-vao-minguar-ubs-alerta-que-sim-entenda-por-que-o-banco-agora-recomenda-venda-das-acoes-bdap/"},
        {"ticker": "USIM5", "bank": "Safra", "date": "2026-05-18", "action": "eleva alvo", "target": "R$ 9,70", "prior_target": "R$ 7,70", "view": "NEUTRAL", "title": "Safra eleva alvo da Usiminas mas alerta pra assimetria negativa", "summary": "Safra elevou o preço-alvo de USIM5 de R$ 7,70 para R$ 9,70 (fim de 2026) após disparada da ação em abril, mas classificou o papel com 'assimetria negativa' — alertando que o espaço para quedas pode ser maior que o potencial adicional de alta, citando riscos ligados a preços do aço e medidas antidumping.", "url": "https://www.seudinheiro.com/2026/empresas/safra-eleva-preco-alvo-de-usiminas-usim5-acoes-sobem-ate-2-lvgb/"},
        {"ticker": "CSNA3", "bank": "Itaú BBA", "date": "2026-04-23", "action": "corta alvo", "target": "R$ 7,50", "prior_target": "R$ 9,50", "view": "NEUTRAL", "title": "Itaú BBA corta alvo da CSN por preocupação com alavancagem", "summary": "Itaú BBA reduziu o preço-alvo de CSNA3 de R$ 9,50 para R$ 7,50, mantendo recomendação neutra. Principal motivo: preocupações crescentes com a alavancagem da empresa, que têm pesado mais sobre o sentimento dos investidores do que o preço elevado do minério de ferro.", "url": "https://www.seudinheiro.com/2026/bolsa-dolar/enferrujou-itau-bba-corta-precos-alvo-de-csn-csna3-e-csn-mineracao-cmin3-outro-banco-tambem-reduz-preco-da-mineradora-kaes/"},
        {"ticker": "MULT3", "bank": "Itaú BBA", "date": "2026-02-06", "action": "mantém alvo", "target": "R$ 36", "prior_target": None, "view": "BULL", "title": "Itaú BBA reitera Multiplan como preferida entre shoppings", "summary": "Itaú BBA reiterou recomendação outperform (compra) para MULT3 com preço-alvo de R$ 36 (fim de 2026) após o resultado do 4T25, mesmo com alta de 22% da ação no ano — banco vê o papel negociando a 13,5x FFO 2026 e 11,0x FFO 2027, com potencial ainda não totalmente precificado mesmo após os benefícios da reforma tributária.", "url": "https://www.suno.com.br/noticias/multiplan-mult3-vale-a-pena-investir-apos-4t25-go/"},
    ]
    ticker_filter = request.args.get('ticker')
    if ticker_filter:
        calls = [c for c in calls if c['ticker'] == ticker_filter.upper()]
    return jsonify(calls)


@app.route('/api/stock-tickers')
def get_stock_tickers():
    resp = get_stock_calls()
    calls = resp.get_json()
    grouped = {}
    for c in calls:
        t = c['ticker']
        if t not in grouped:
            grouped[t] = {"ticker": t, "company": TICKER_NAMES.get(t, t), "count": 0, "last_date": c['date']}
        grouped[t]['count'] += 1
        if c['date'] > grouped[t]['last_date']:
            grouped[t]['last_date'] = c['date']
    tickers = sorted(grouped.values(), key=lambda x: x['ticker'])
    return jsonify(tickers)


@app.route('/api/stock-quote')
def get_stock_quote():
    ticker = request.args.get('ticker', '').upper().strip()
    if not ticker:
        return jsonify({'error': 'ticker é obrigatório'}), 400
    yf_ticker = ticker if '.' in ticker else f'{ticker}.SA'

    range_param = request.args.get('range', '1y')
    period_map = {'3mo': '3mo', '6mo': '6mo', '1y': '1y', '2y': '2y', 'ytd': 'ytd', 'max': 'max'}
    period = period_map.get(range_param, '1y')

    try:
        stock = yf.Ticker(yf_ticker)
        hist = stock.history(period=period, interval='1d')

        if hist.empty:
            return jsonify({'error': f'Sem dados para {ticker}'}), 404

        hist = hist.reset_index()
        data = []
        for _, row in hist.iterrows():
            ts = row['Date']
            if isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()
            data.append({
                'date': ts.strftime('%Y-%m-%d'),
                'open': round(float(row['Open']), 2),
                'high': round(float(row['High']), 2),
                'low': round(float(row['Low']), 2),
                'close': round(float(row['Close']), 2),
                'volume': int(row['Volume'])
            })

        quote = stock.history(period='5d', interval='1d')
        current_price = None
        change = None
        change_pct = None
        if not quote.empty:
            last = quote.iloc[-1]
            current_price = round(float(last['Close']), 2)
            if len(quote) > 1:
                prev_close = round(float(quote.iloc[-2]['Close']), 2)
                change = round(current_price - prev_close, 2)
                change_pct = round((change / prev_close) * 100, 2)
            else:
                change = 0
                change_pct = 0

        return jsonify({
            'ticker': ticker,
            'company': TICKER_NAMES.get(ticker, ticker),
            'data': data,
            'current': {
                'price': current_price or data[-1]['close'],
                'change': change,
                'changePercent': change_pct
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/market-data')
def get_market_data():
    config = [
        ('WINFUT',   '^BVSP'),      # B3 WIN futures not on yfinance; using IBOV spot (same intraday Δ)
        ('WDOFUT',   'USDBRL=X'),   # B3 WDO futures not on yfinance; using USD/BRL spot
        ('DI1F2033', None),         # B3 DI futures not on yfinance
        ('DXY',      'DX-Y.NYB'),
        ('US10Y',    '^TNX'),
        ('VIX',      '^VIX'),
    ]

    def fetch_one(name, ticker):
        if ticker is None:
            return name, None
        try:
            hist = yf.Ticker(ticker).history(period='5d')
            if len(hist) >= 1:
                price = float(hist['Close'].iloc[-1])
                prev  = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else price
                chg   = price - prev
                chg_pct = (chg / prev * 100) if prev else 0
                return name, {'price': round(price, 4), 'change': round(chg, 4), 'change_pct': round(chg_pct, 2)}
        except:
            pass
        return name, None

    result = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(fetch_one, n, t) for n, t in config]
        for f in concurrent.futures.as_completed(futs):
            name, data = f.result()
            result[name] = data

    return jsonify(result)


@app.route('/api/movers')
def get_movers():
    tickers = [
        'PETR4.SA','VALE3.SA','ITUB4.SA','BBDC4.SA','BBAS3.SA',
        'ABEV3.SA','WEGE3.SA','RENT3.SA','ELET3.SA','RDOR3.SA',
        'PRIO3.SA','SUZB3.SA','EQTL3.SA','SBSP3.SA','BPAC11.SA',
        'VIVT3.SA','EMBR3.SA','GGBR4.SA','JBSS3.SA','NTCO3.SA',
        'RADL3.SA','HAPV3.SA','LREN3.SA','BRFS3.SA','MGLU3.SA',
    ]
    try:
        data = yf.download(tickers, period='5d', group_by='ticker', progress=False, auto_adjust=True)
        results = []
        for ticker in tickers:
            try:
                closes = data[ticker]['Close'].dropna()
                if len(closes) >= 2:
                    price = float(closes.iloc[-1])
                    prev  = float(closes.iloc[-2])
                    if prev > 0:
                        chg_pct = (price - prev) / prev * 100
                        results.append({
                            'ticker': ticker.replace('.SA', ''),
                            'price': round(price, 2),
                            'change_pct': round(chg_pct, 2)
                        })
                elif len(closes) == 1:
                    results.append({
                        'ticker': ticker.replace('.SA', ''),
                        'price': round(float(closes.iloc[-1]), 2),
                        'change_pct': 0.0
                    })
            except:
                pass
        results.sort(key=lambda x: x['change_pct'], reverse=True)
        gainers = results[:5]
        losers  = sorted(results, key=lambda x: x['change_pct'])[:5]
        return jsonify({'gainers': gainers, 'losers': losers})
    except Exception as e:
        return jsonify({'gainers': [], 'losers': [], 'error': str(e)})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'Servidor rodando em http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=False)
