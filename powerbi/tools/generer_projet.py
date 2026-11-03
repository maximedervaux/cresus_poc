import csv, json, re, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'powerbi'
S = P / 'Cresus.SemanticModel'
R = P / 'Cresus.Report'
def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
def js(path, obj): put(path, json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
base = 'https://developer.microsoft.com/json-schemas/fabric/item/report/'
js(P/'Cresus.pbip', {'$schema':'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json','version':'1.0','artifacts':[{'report':{'path':'Cresus.Report'}}],'settings':{'enableAutoRecovery':True}})
js(S/'definition.pbism', {'$schema':'https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json','version':'4.0','settings':{}})
put(S/'definition/database.tmdl', 'database\n\tcompatibilityLevel: 1601\n')
put(S/'definition/model.tmdl', 'model Model\n\tculture: fr-FR\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-US\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\tannotation __PBI_TimeIntelligenceEnabled = 0\n')
params = [('ServeurMySQL','localhost:3306'),('BaseMySQL','cresus_poc'),('ModeSource','MySQL'),('DossierExports',str(ROOT/'exports'))]
put(S/'definition/expressions.tmdl', '\n\n'.join('expression '+k+' = '+json.dumps(v)+' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n\tannotation PBI_ResultType = Text' for k,v in params)+'\n')
tables = {}
text_cols = {'code_devise','libelle_devise','nom_filiale','pays','zone_geo','devise_principale','libelle','sens','statut','type_run','modele','type_choc','libelle_scenario','source','statut_liquidite','indicateur'}
integer_cols = {'date_id','jour','mois','annee','jour_semaine','ouvre_fra','ouvre_can','ouvre_civ','retenu','modele_retenu','nb_jours','nb_jours_sous_seuil','lignes_lues','doublons','non_pertinentes','rejets','lignes_chargees'}
for file in sorted((ROOT/'exports').glob('*.csv')):
    rows = list(csv.DictReader(file.open(encoding='utf-8-sig',newline='')))
    cols = list(rows[0]); name=file.stem; tables[name]=cols
    t = 'table '+name+'\n'
    if name=='dim_calendrier': t+='\tdataCategory: Time\n'
    types=[]
    for c in cols:
        if c in text_cols: dt,mt='string','type text'
        elif c=='date_execution': dt,mt='dateTime','type datetime'
        elif c=='date' or c.startswith('date_') and c!='date_id': dt,mt='dateTime','type date'
        elif c.startswith('id_') or c in integer_cols: dt,mt='int64','Int64.Type'
        elif 'taux' in c or c in {'variation_pct','wape_pct','valeur_choc'} or name=='fait_prevision_taux' and c.startswith('borne_') or name=='v_projection_taux' and c.startswith('borne_'): dt,mt='double','type number'
        else: dt,mt='decimal','Currency.Type'
        types.append('{"'+c+'", '+mt+'}')
        t+='\n\tcolumn '+c+'\n\t\tdataType: '+dt+'\n\t\tsourceColumn: '+c+'\n\t\tsummarizeBy: none\n'
        if dt=='dateTime': t+='\t\tformatString: dd/MM/yyyy'+(' HH:mm' if mt=='type datetime' else '')+'\n'
        if name=='dim_calendrier' and c=='date': t+='\t\tisKey\n\t\tannotation UnderlyingDateTimeDataType = Date\n'
    t+='\n\tpartition '+name+' = m\n\t\tmode: import\n\t\tsource =\n'
    m=['let', '    Source = if ModeSource = "CSV" then', '        Table.PromoteHeaders(Csv.Document(File.Contents(DossierExports & "\\'+name+'.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]), [PromoteAllScalars=true])', '    else if ModeSource = "MySQL" then', '        MySQL.Database(ServeurMySQL, BaseMySQL, [ReturnSingleDatabase=true, CreateNavigationProperties=false, Query="SELECT * FROM `'+name+'`"])', '    else error "ModeSource doit valoir MySQL ou CSV",', '    Types = Table.TransformColumnTypes(Source, {'+', '.join(types)+'}, "en-US")', 'in', '    Types']
    t+='\n'.join('\t\t\t\t'+line for line in m)+'\n'
    put(S/'definition/tables'/f'{name}.tmdl',t)
rels=[]
def rel(a,b,c,d=None):
    rels.append('relationship '+str(uuid.uuid5(uuid.NAMESPACE_URL,a+c+b))+'\n\tfromColumn: '+a+'.'+c+'\n\ttoColumn: '+b+'.'+(d or c)+'\n\tcrossFilteringBehavior: oneDirection\n')
for a,cs in {'fait_flux_tresorerie':['date_id','id_filiale','code_devise','id_type_flux'],'fait_taux':['date_id','code_devise'],'fait_prevision':['id_filiale'],'fait_prevision_taux':['code_devise'],'fait_scenario_stress':['id_filiale'],'perf_modele':['id_filiale'],'v_position_realisee':['id_filiale'],'v_position_projetee':['id_filiale'],'v_backtest':['id_filiale'],'v_stress_synthese':['id_filiale'],'v_projection_taux':['code_devise']}.items():
    for c in cs: rel(a,{'date_id':'dim_calendrier','id_filiale':'dim_filiale','code_devise':'dim_devise','id_type_flux':'dim_type_flux'}[c],c)
for a,c in [('fait_prevision','date_cible'),('fait_prevision_taux','date_cible'),('fait_scenario_stress','date_cible'),('v_position_realisee','date'),('v_position_projetee','date'),('v_backtest','date')]: rel(a,'dim_calendrier',c,'date')
put(S/'definition/relationships.tmdl','\n'.join(rels))
measures={
'Position actuelle USD':'VAR d = MAX(v_position_realisee[date]) RETURN CALCULATE(SUM(v_position_realisee[position_usd]), v_position_realisee[date] = d)',
'Devises en alerte':'VAR d = MAX(v_position_realisee[date]) RETURN CALCULATE(COUNTROWS(v_position_realisee), v_position_realisee[date] = d, v_position_realisee[statut_liquidite] = "ALERTE")',
'Position J+30 USD (modèle retenu)':'VAR d = MAX(v_position_projetee[date]) RETURN CALCULATE(SUM(v_position_projetee[position_projetee_usd]), v_position_projetee[date] = d, v_position_projetee[modele_retenu] = 1)',
'Flux net réalisé USD':'CALCULATE(SUMX(fait_flux_tresorerie, IF(RELATED(dim_type_flux[sens]) = "ENCAISSEMENT", 1, -1) * fait_flux_tresorerie[montant_usd]), fait_flux_tresorerie[statut] = "REALISE")',
'MAE backtest':'IF(HASONEVALUE(dim_filiale[id_filiale]), AVERAGEX(v_backtest, ABS(v_backtest[flux_prevu] - v_backtest[flux_reel])))',
'Gain vs prévision manuelle %':'VAR m = CALCULATE(AVERAGE(perf_modele[mae]), perf_modele[retenu] = 1) VAR b = CALCULATE(AVERAGE(perf_modele[mae]), perf_modele[modele] = "MANUEL") RETURN IF(HASONEVALUE(dim_filiale[id_filiale]), DIVIDE(b-m,b))',
'Impact stress USD':'IF(HASONEVALUE(_Scenarios[libelle_scenario]), SUM(v_stress_synthese[impact_usd]))',
'Jours sous seuil (stress)':'IF(HASONEVALUE(_Scenarios[libelle_scenario]), SUM(v_stress_synthese[nb_jours_sous_seuil]))',
'Seuil actuel USD':'VAR d = MAX(v_position_realisee[date]) RETURN CALCULATE(SUM(v_position_realisee[seuil_alerte_usd]), v_position_realisee[date] = d)',
'Écart au seuil USD':'[Position actuelle USD] - [Seuil actuel USD]',
'Position réalisée USD':'SUM(v_position_realisee[position_usd])',
'Position projetée USD':'CALCULATE(SUM(v_position_projetee[position_projetee_usd]), v_position_projetee[modele_retenu] = 1)',
'Taux prévu':'IF(HASONEVALUE(dim_devise[code_devise]) && HASONEVALUE(fait_prevision_taux[modele]), AVERAGE(fait_prevision_taux[taux_prevu]))',
'Borne basse taux':'IF(HASONEVALUE(dim_devise[code_devise]) && HASONEVALUE(fait_prevision_taux[modele]), AVERAGE(fait_prevision_taux[borne_basse]))',
'Borne haute taux':'IF(HASONEVALUE(dim_devise[code_devise]) && HASONEVALUE(fait_prevision_taux[modele]), AVERAGE(fait_prevision_taux[borne_haute]))',
'Flux réel backtest':'IF(HASONEVALUE(dim_filiale[id_filiale]), AVERAGE(v_backtest[flux_reel]))',
'Flux prévu backtest':'IF(HASONEVALUE(dim_filiale[id_filiale]) && HASONEVALUE(v_backtest[modele]), AVERAGE(v_backtest[flux_prevu]))',
'Position base stress USD':'IF(HASONEVALUE(_Scenarios[libelle_scenario]), SUM(fait_scenario_stress[position_base_usd]))',
'Position stressée USD':'IF(HASONEVALUE(_Scenarios[libelle_scenario]), SUM(fait_scenario_stress[position_stressee_usd]))',
'Couleur alerte':'IF([Écart au seuil USD] < 0, "#C62828", "#16856B")',
}
t='table _Mesures\n\tcolumn Masquer\n\t\tdataType: int64\n\t\tisHidden\n\t\tsourceColumn: Masquer\n\tpartition _Mesures = m\n\t\tmode: import\n\t\tsource = #table(type table [Masquer=Int64.Type], {})\n'
for n,e in measures.items():
    fmt='0.0%' if n.endswith('%') else '#,0.0,," M USD"' if 'USD' in n else '0.000000' if 'taux' in n.lower() or n=='Taux prévu' else '#,0.00' if 'backtest' in n else '0'
    t+="\n\tmeasure '"+n+"' = "+e+'\n\t\tformatString: '+fmt+'\n'
put(S/'definition/tables/_Mesures.tmdl',t)
put(S/'definition/tables/_Scenarios.tmdl', 'table _Scenarios\n\tcolumn libelle_scenario\n\t\tdataType: string\n\t\tsourceColumn: libelle_scenario\n\t\tsummarizeBy: none\n\tpartition _Scenarios = m\n\t\tmode: import\n\t\tsource = Table.Distinct(Table.SelectColumns(fait_scenario_stress, {"libelle_scenario"}))\n')
for a in ['fait_scenario_stress','v_stress_synthese']: rel(a,'_Scenarios','libelle_scenario')
put(S/'definition/relationships.tmdl','\n'.join(rels))
js(R/'definition.pbir',{'$schema':base+'definitionProperties/2.0.0/schema.json','version':'4.0','datasetReference':{'byPath':{'path':'../Cresus.SemanticModel'}}})
js(R/'definition/version.json',{'$schema':base+'definition/versionMetadata/1.0.0/schema.json','version':'2.0.0'})
js(R/'definition/report.json',{'$schema':base+'definition/report/3.1.0/schema.json','themeCollection':{}})
pages=['Actifs & liquidité','Projection des devises','Fiabilité des prévisions','Scénarios de stress','Qualité des données']
ids=['page'+str(i+1) for i in range(5)]
js(R/'definition/pages/pages.json',{'$schema':base+'definition/pagesMetadata/1.0.0/schema.json','pageOrder':ids,'activePageName':ids[0]})
def col(t,c): return {'field':{'Column':{'Expression':{'SourceRef':{'Entity':t}},'Property':c}},'queryRef':t+'.'+c,'nativeQueryRef':c}
def mea(n): return {'field':{'Measure':{'Expression':{'SourceRef':{'Entity':'_Mesures'}},'Property':n}},'queryRef':'_Mesures.'+n,'nativeQueryRef':n}
count=0
def visual(page,typ,title,x,y,w,h,roles):
    global count
    count+=1; name='visual'+str(count)
    title_props={'show':{'expr':{'Literal':{'Value':'true'}}},'text':{'expr':{'Literal':{'Value':"'"+title.replace("'","''")+"'"}}}}
    obj={'$schema':base+'definition/visualContainer/2.1.0/schema.json','name':name,'position':{'x':x,'y':y,'width':w,'height':h,'z':count,'tabOrder':count},'visual':{'visualType':typ,'query':{'queryState':{k:{'projections':v} for k,v in roles.items()}},'visualContainerObjects':{'title':[{'properties':title_props}]}}}
    js(R/'definition/pages'/page/'visuals'/name/'visual.json',obj)
for pid,title in zip(ids,pages): js(R/'definition/pages'/pid/'page.json',{'$schema':base+'definition/page/2.0.0/schema.json','name':pid,'displayName':title,'displayOption':'FitToPage','width':1280,'height':900})
def slicer(p,t,c,x=24,y=20,w=440): visual(p,'slicer','Filtrer : '+c,x,y,w,90,{'Values':[col(t,c)]})
slicer('page1','dim_filiale','nom_filiale')
for i,n in enumerate(['Position actuelle USD','Position J+30 USD (modèle retenu)','Devises en alerte']): visual('page1','card',n,24+i*416,125,400,110,{'Values':[mea(n)]})
visual('page1','clusteredColumnChart','Positions actuelles et seuils — M USD',24,250,600,280,{'Category':[col('dim_filiale','nom_filiale')],'Y':[mea('Position actuelle USD'),mea('Seuil actuel USD')]})
visual('page1','lineChart','Réalisé et projection retenue — USD',650,250,600,280,{'Category':[col('dim_calendrier','date')],'Y':[mea('Position réalisée USD'),mea('Position projetée USD')]})
visual('page1','tableEx','Stocks par filiale — écart négatif = ALERTE',24,550,1226,300,{'Values':[col('dim_filiale','nom_filiale'),col('dim_filiale','devise_principale'),mea('Position actuelle USD'),mea('Seuil actuel USD'),mea('Écart au seuil USD')]})
slicer('page2','dim_devise','code_devise'); slicer('page2','fait_prevision_taux','modele',650)
visual('page2','lineChart','Sélectionner une devise et un modèle — prévision et bornes 80 %',24,125,1226,360,{'Category':[col('dim_calendrier','date')],'Y':[mea('Taux prévu'),mea('Borne basse taux'),mea('Borne haute taux')]})
visual('page2','tableEx','Signal de change à J+30',24,510,1226,330,{'Values':[col('v_projection_taux',c) for c in tables['v_projection_taux']]})
slicer('page3','dim_filiale','nom_filiale')
slicer('page3','v_backtest','modele',480,20,320)
visual('page3','card','Gain vs manuel — une filiale',830,20,420,90,{'Values':[mea('Gain vs prévision manuelle %')]})
visual('page3','lineChart','Backtest en devise locale — sélectionner une filiale et un modèle',24,125,1226,350,{'Category':[col('dim_calendrier','date')],'Y':[mea('Flux réel backtest'),mea('Flux prévu backtest')]})
visual('page3','tableEx','Performances — montants en devise locale ; WAPE en points %',24,500,1226,340,{'Values':[col('perf_modele',c) for c in tables['perf_modele']]})
slicer('page4','_Scenarios','libelle_scenario',24,20,600); slicer('page4','dim_filiale','nom_filiale',650)
visual('page4','lineChart','Sélectionner un scénario — positions en USD',24,130,780,350,{'Category':[col('dim_calendrier','date')],'Y':[mea('Position base stress USD'),mea('Position stressée USD')]})
visual('page4','clusteredColumnChart','Impact J+30 — USD',830,130,420,350,{'Category':[col('dim_filiale','nom_filiale')],'Y':[mea('Impact stress USD')]})
visual('page4','tableEx','Stress par filiale et scénario',24,510,1226,330,{'Values':[col('v_stress_synthese',c) for c in ['libelle_scenario','nom_filiale','position_base_j30_usd','position_stressee_j30_usd','impact_usd','nb_jours_sous_seuil']]})
visual('page5','tableEx','Contrôles ETL par source et date',24,40,1226,760,{'Values':[col('etl_controle_qualite',c) for c in tables['etl_controle_qualite']]})
print(f'Créé : {len(tables)} objets source, {len(rels)} relations, {len(measures)} mesures, 5 pages, {count} visuels')

