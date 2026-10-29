"""开发新代理的邮件模板：英文主文 + 各目标国家语言版本。

译文由 AI 翻译，正式群发前建议请母语人士快速校对一遍（尤其是格鲁吉亚语、亚美尼亚语）。
{name} 会替换成联系人名字或机构名。
"""

COUNTRY_LANG = {
    "Czech Republic": "cs", "Czechia": "cs", "Slovakia": "sk", "Poland": "pl", "Hungary": "hu",
    "Austria": "de", "Germany": "de", "Switzerland": "de", "Italy": "it", "San Marino": "it", "Turkey": "tr", "Türkiye": "tr", "Georgia": "ka", "Armenia": "hy",
    "Mexico": "es", "Colombia": "es", "Peru": "es", "Chile": "es", "Brazil": "pt",
    "Thailand": "th", "Vietnam": "vi", "South Korea": "ko", "Korea": "ko", "Japan": "ja",
}
COUNTRY_ZH = {
    "Czech Republic": "捷克", "Slovakia": "斯洛伐克", "Poland": "波兰", "Hungary": "匈牙利", "Austria": "奥地利",
    "Germany": "德国", "Switzerland": "瑞士", "Italy": "意大利", "Turkey": "土耳其", "Georgia": "格鲁吉亚", "Armenia": "亚美尼亚", "Mexico": "墨西哥",
    "Colombia": "哥伦比亚", "Brazil": "巴西", "Thailand": "泰国", "Vietnam": "越南", "South Korea": "韩国",
    "Japan": "日本", "India": "印度", "Nepal": "尼泊尔", "Peru": "秘鲁",
}
TARGET_REGIONS = {
    "东欧": ["Czech Republic", "Slovakia", "Poland", "Hungary", "Austria"],
    "德语区 / 意大利": ["Germany", "Switzerland", "Austria", "Italy"],
    "土耳其 / 高加索": ["Turkey", "Georgia", "Armenia"],
    "拉美": ["Mexico", "Brazil", "Colombia"],
    "东南亚": ["Thailand", "Vietnam"],
    "东亚": ["South Korea", "Japan"],
}

STATS = """362 Graduates | 1,900+ University Offers | 5.3 Offers per Graduate
• 242 — University of Toronto
• 125 — University of British Columbia (UBC)
• 57 — McMaster University
• 39 — University of Waterloo
• 37 — McGill University
• 34 — University College London (UCL)"""

LINK = "https://calendly.com/polozhang-cseec/30min"

EN = {
    "label": "English",
    "subject": "Vancouver Grade 8–12 School Partnership | 1,900+ University Offers",
    "body": f"""Dear {{name}},

Greetings from Vancouver, Canada!

I'm Polo Zhang from Johnathan Academy, a British Columbia independent secondary school in Vancouver serving students from Grades 8–12.

We are currently expanding our international recruitment network and looking to establish long-term partnerships with selected professional education agencies.

What distinguishes Johnathan Academy is our strong focus on academics, university preparation, and long-term student success.

Strong University Outcomes
Across our educational network, our 2024–2026 graduating classes achieved:
{STATS}

Our graduates have also received offers from Imperial College London, King's College London, the University of Edinburgh, the University of Melbourne, the University of Sydney, Queen's University, Western University, Simon Fraser University, and many other leading institutions.

Why Johnathan Academy?
• Grades 8–12 education in Vancouver
• BC Curriculum & Dogwood Diploma pathway
• Strong academic and university preparation
• AP and advanced academic opportunities
• Individualized academic and university planning
• Earlier entry into Canada to build a stronger academic record before Grade 12

If your students and families are looking for an academically focused Canadian secondary school with strong university outcomes, we would be very pleased to explore a partnership with you.

Book a convenient 30-minute online meeting with me here:
{LINK}
You are also welcome to reply directly to this email.

Warm regards,
Polo Zhang
Johnathan Academy, Vancouver, Canada""",
}

T = {}

T["es"] = ("Español", "Alianza con un colegio de grados 8–12 en Vancouver | Más de 1.900 admisiones universitarias", f"""Estimado/a {{name}}:

¡Saludos desde Vancouver, Canadá!

Mi nombre es Polo Zhang y represento a Johnathan Academy, un colegio secundario independiente de British Columbia, ubicado en Vancouver, para estudiantes de 8.º a 12.º grado.

Estamos ampliando nuestra red internacional de reclutamiento y buscamos establecer alianzas a largo plazo con agencias educativas profesionales seleccionadas.

Lo que distingue a Johnathan Academy es nuestro fuerte enfoque académico, la preparación universitaria y el éxito de nuestros estudiantes a largo plazo.

Excelentes resultados universitarios
En nuestra red educativa, las promociones de 2024–2026 lograron:
{STATS}

Nuestros egresados también recibieron ofertas de Imperial College London, King's College London, la Universidad de Edimburgo, la Universidad de Melbourne, la Universidad de Sídney, Queen's University, Western University, Simon Fraser University y muchas otras instituciones de prestigio.

¿Por qué Johnathan Academy?
• Educación de 8.º a 12.º grado en Vancouver
• Currículo de British Columbia y Diploma Dogwood
• Sólida preparación académica y universitaria
• Cursos AP y oportunidades académicas avanzadas
• Planificación académica y universitaria personalizada
• Ingreso temprano a Canadá para construir un expediente académico sólido antes del grado 12

Si sus estudiantes y familias buscan un colegio secundario canadiense con enfoque académico y excelentes resultados universitarios, nos encantaría explorar una alianza con ustedes.

Puede reservar una reunión en línea de 30 minutos conmigo aquí:
{LINK}
También puede responder directamente a este correo.

Atentamente,
Polo Zhang
Johnathan Academy, Vancouver, Canadá""")

T["pt"] = ("Português (Brasil)", "Parceria com escola de 8º ao 12º ano em Vancouver | Mais de 1.900 aprovações universitárias", f"""Prezado(a) {{name}},

Saudações de Vancouver, Canadá!

Meu nome é Polo Zhang e represento a Johnathan Academy, uma escola de ensino médio independente da Colúmbia Britânica, em Vancouver, que atende alunos do 8º ao 12º ano (Grades 8–12).

Estamos ampliando nossa rede internacional de recrutamento e buscamos estabelecer parcerias de longo prazo com agências de intercâmbio profissionais selecionadas.

O que diferencia a Johnathan Academy é o nosso forte foco acadêmico, a preparação para a universidade e o sucesso dos alunos a longo prazo.

Excelentes resultados universitários
Em nossa rede educacional, as turmas de formandos de 2024–2026 alcançaram:
{STATS}

Nossos formandos também receberam ofertas do Imperial College London, King's College London, Universidade de Edimburgo, Universidade de Melbourne, Universidade de Sydney, Queen's University, Western University, Simon Fraser University e muitas outras instituições renomadas.

Por que a Johnathan Academy?
• Ensino do 8º ao 12º ano em Vancouver
• Currículo da Colúmbia Britânica e Dogwood Diploma
• Forte preparação acadêmica e universitária
• Disciplinas AP e oportunidades acadêmicas avançadas
• Planejamento acadêmico e universitário individualizado
• Chegada mais cedo ao Canadá para construir um histórico acadêmico sólido antes do 12º ano

Se os seus alunos e famílias procuram uma escola canadense com foco acadêmico e excelentes resultados universitários, teremos muito prazer em explorar uma parceria com vocês.

Agende uma reunião online de 30 minutos comigo aqui:
{LINK}
Você também pode responder diretamente a este e-mail.

Atenciosamente,
Polo Zhang
Johnathan Academy, Vancouver, Canadá""")

T["cs"] = ("Čeština", "Partnerství se střední školou (8.–12. ročník) ve Vancouveru | Více než 1 900 nabídek z univerzit", f"""Vážená paní / Vážený pane {{name}},

srdečný pozdrav z Vancouveru v Kanadě!

Jmenuji se Polo Zhang a zastupuji Johnathan Academy, nezávislou střední školu v Britské Kolumbii se sídlem ve Vancouveru, která vzdělává studenty 8.–12. ročníku.

V současné době rozšiřujeme naši mezinárodní náborovou síť a hledáme dlouhodobé partnerství s vybranými profesionálními vzdělávacími agenturami.

Johnathan Academy se vyznačuje silným důrazem na akademické výsledky, přípravu na univerzitu a dlouhodobý úspěch studentů.

Výborné výsledky při přijímání na univerzity
V rámci naší vzdělávací sítě dosáhli absolventi ročníků 2024–2026:
{STATS}

Naši absolventi získali také nabídky od Imperial College London, King's College London, University of Edinburgh, University of Melbourne, University of Sydney, Queen's University, Western University, Simon Fraser University a mnoha dalších předních institucí.

Proč Johnathan Academy?
• Vzdělávání 8.–12. ročníku ve Vancouveru
• Kurikulum Britské Kolumbie a diplom Dogwood
• Kvalitní akademická příprava a příprava na univerzitu
• Kurzy AP a pokročilé akademické příležitosti
• Individuální studijní a univerzitní plánování
• Dřívější příjezd do Kanady pro vybudování silných studijních výsledků před 12. ročníkem

Pokud vaši studenti a rodiny hledají akademicky zaměřenou kanadskou střední školu s výbornými výsledky při přijímání na univerzity, rádi s vámi prodiskutujeme možnou spolupráci.

Třicetiminutovou online schůzku si můžete rezervovat zde:
{LINK}
Můžete také přímo odpovědět na tento e-mail.

S pozdravem
Polo Zhang
Johnathan Academy, Vancouver, Kanada""")

T["sk"] = ("Slovenčina", "Partnerstvo so strednou školou (8.–12. ročník) vo Vancouveri | Viac ako 1 900 ponúk z univerzít", f"""Vážená pani / Vážený pán {{name}},

srdečný pozdrav z Vancouveru v Kanade!

Volám sa Polo Zhang a zastupujem Johnathan Academy, nezávislú strednú školu v Britskej Kolumbii so sídlom vo Vancouveri, ktorá vzdeláva študentov 8.–12. ročníka.

V súčasnosti rozširujeme našu medzinárodnú náborovú sieť a hľadáme dlhodobé partnerstvo s vybranými profesionálnymi vzdelávacími agentúrami.

Johnathan Academy sa vyznačuje silným dôrazom na akademické výsledky, prípravu na univerzitu a dlhodobý úspech študentov.

Výborné výsledky pri prijímaní na univerzity
V rámci našej vzdelávacej siete dosiahli absolventi ročníkov 2024–2026:
{STATS}

Naši absolventi získali aj ponuky od Imperial College London, King's College London, University of Edinburgh, University of Melbourne, University of Sydney, Queen's University, Western University, Simon Fraser University a mnohých ďalších popredných inštitúcií.

Prečo Johnathan Academy?
• Vzdelávanie 8.–12. ročníka vo Vancouveri
• Kurikulum Britskej Kolumbie a diplom Dogwood
• Kvalitná akademická príprava a príprava na univerzitu
• Kurzy AP a pokročilé akademické príležitosti
• Individuálne študijné a univerzitné plánovanie
• Skorší príchod do Kanady na vybudovanie silných študijných výsledkov pred 12. ročníkom

Ak vaši študenti a rodiny hľadajú akademicky zameranú kanadskú strednú školu s výbornými výsledkami pri prijímaní na univerzity, radi s vami prediskutujeme možnú spoluprácu.

30-minútové online stretnutie si môžete rezervovať tu:
{LINK}
Môžete tiež priamo odpovedať na tento e-mail.

S pozdravom
Polo Zhang
Johnathan Academy, Vancouver, Kanada""")

T["pl"] = ("Polski", "Partnerstwo ze szkołą średnią (klasy 8–12) w Vancouver | Ponad 1900 ofert z uniwersytetów", f"""Szanowni Państwo / {{name}},

serdeczne pozdrowienia z Vancouver w Kanadzie!

Nazywam się Polo Zhang i reprezentuję Johnathan Academy – niezależną szkołę średnią w Kolumbii Brytyjskiej, w Vancouver, kształcącą uczniów klas 8–12.

Obecnie rozbudowujemy naszą międzynarodową sieć rekrutacyjną i chcemy nawiązać długoterminową współpracę z wybranymi profesjonalnymi agencjami edukacyjnymi.

Johnathan Academy wyróżnia się silnym naciskiem na wyniki akademickie, przygotowanie do studiów i długofalowy sukces uczniów.

Bardzo dobre wyniki rekrutacji na uczelnie
W naszej sieci edukacyjnej absolwenci roczników 2024–2026 osiągnęli:
{STATS}

Nasi absolwenci otrzymali również oferty z Imperial College London, King's College London, University of Edinburgh, University of Melbourne, University of Sydney, Queen's University, Western University, Simon Fraser University i wielu innych renomowanych uczelni.

Dlaczego Johnathan Academy?
• Nauka w klasach 8–12 w Vancouver
• Program nauczania Kolumbii Brytyjskiej i dyplom Dogwood
• Solidne przygotowanie akademickie i do studiów
• Kursy AP i zaawansowane możliwości akademickie
• Indywidualne planowanie nauki i ścieżki na studia
• Wcześniejszy przyjazd do Kanady, aby zbudować mocne wyniki przed klasą 12

Jeśli Państwa uczniowie i ich rodziny szukają kanadyjskiej szkoły średniej nastawionej na wyniki akademickie i skuteczne przygotowanie do studiów, chętnie porozmawiamy o współpracy.

Zapraszam do umówienia 30-minutowego spotkania online:
{LINK}
Można też po prostu odpowiedzieć na tę wiadomość.

Z wyrazami szacunku
Polo Zhang
Johnathan Academy, Vancouver, Kanada""")

T["hu"] = ("Magyar", "Partnerség egy vancouveri 8–12. évfolyamos középiskolával | Több mint 1900 egyetemi felvételi ajánlat", f"""Tisztelt {{name}}!

Üdvözlöm Vancouverből, Kanadából!

Polo Zhang vagyok, a Johnathan Academy képviselője. Iskolánk Brit Columbia tartomány független középiskolája Vancouverben, 8–12. évfolyamos diákok számára.

Jelenleg bővítjük nemzetközi toborzási hálózatunkat, és hosszú távú partnerséget szeretnénk kialakítani kiválasztott, professzionális oktatási ügynökségekkel.

A Johnathan Academy-t az erős akadémiai fókusz, az egyetemi felkészítés és a diákok hosszú távú sikere különbözteti meg.

Kiváló egyetemi eredmények
Oktatási hálózatunkban a 2024–2026-os végzős évfolyamok eredményei:
{STATS}

Végzőseink ajánlatot kaptak többek között az Imperial College London, a King's College London, az Edinburgh-i Egyetem, a Melbourne-i Egyetem, a Sydney-i Egyetem, a Queen's University, a Western University és a Simon Fraser University intézményeitől is.

Miért a Johnathan Academy?
• 8–12. évfolyamos oktatás Vancouverben
• Brit Columbia-i tanterv és Dogwood érettségi diploma
• Erős akadémiai és egyetemi felkészítés
• AP kurzusok és emelt szintű tanulmányi lehetőségek
• Egyéni tanulmányi és egyetemi tervezés
• Korábbi érkezés Kanadába, hogy a diák a 12. évfolyam előtt erős tanulmányi eredményeket építhessen

Ha diákjaik és a családok akadémiailag erős kanadai középiskolát keresnek kiváló egyetemi eredményekkel, örömmel megvizsgálnánk az együttműködés lehetőségét.

30 perces online megbeszélést itt foglalhat:
{LINK}
Természetesen erre az e-mailre is válaszolhat.

Üdvözlettel:
Polo Zhang
Johnathan Academy, Vancouver, Kanada""")

T["de"] = ("Deutsch", "Partnerschaft mit einer Schule für die Klassen 8–12 in Vancouver | Über 1.900 Studienplatzangebote", f"""Sehr geehrte/r {{name}},

herzliche Grüße aus Vancouver, Kanada!

Mein Name ist Polo Zhang, ich vertrete die Johnathan Academy, eine unabhängige Sekundarschule in British Columbia mit Sitz in Vancouver für Schülerinnen und Schüler der Klassen 8–12.

Wir bauen derzeit unser internationales Rekrutierungsnetzwerk aus und suchen langfristige Partnerschaften mit ausgewählten professionellen Bildungsagenturen.

Die Johnathan Academy zeichnet sich durch einen klaren akademischen Schwerpunkt, gezielte Studienvorbereitung und den langfristigen Erfolg ihrer Schüler aus.

Starke Ergebnisse bei der Hochschulzulassung
In unserem Schulnetzwerk erzielten die Abschlussjahrgänge 2024–2026:
{STATS}

Unsere Absolventen erhielten außerdem Zusagen vom Imperial College London, King's College London, der University of Edinburgh, der University of Melbourne, der University of Sydney, der Queen's University, der Western University, der Simon Fraser University und vielen weiteren renommierten Hochschulen.

Warum Johnathan Academy?
• Unterricht der Klassen 8–12 in Vancouver
• Lehrplan von British Columbia und Dogwood Diploma
• Solide akademische Ausbildung und Studienvorbereitung
• AP-Kurse und weiterführende akademische Angebote
• Individuelle Lern- und Studienplanung
• Früherer Einstieg in Kanada, um vor der 12. Klasse ein starkes Notenprofil aufzubauen

Wenn Ihre Schüler und Familien eine akademisch ausgerichtete kanadische Sekundarschule mit starken Studienergebnissen suchen, würden wir uns sehr über eine Zusammenarbeit freuen.

Hier können Sie ein 30-minütiges Online-Gespräch mit mir buchen:
{LINK}
Gerne können Sie auch direkt auf diese E-Mail antworten.

Mit freundlichen Grüßen
Polo Zhang
Johnathan Academy, Vancouver, Kanada""")

T["tr"] = ("Türkçe", "Vancouver'da 8–12. Sınıf Okulu ile Ortaklık | 1.900'den Fazla Üniversite Kabulü", f"""Sayın {{name}},

Kanada, Vancouver'dan selamlar!

Ben Polo Zhang, Johnathan Academy adına yazıyorum. Okulumuz, Vancouver'da 8–12. sınıf öğrencilerine eğitim veren, British Columbia eyaletine bağlı bağımsız bir ortaöğretim kurumudur.

Uluslararası öğrenci ağımızı genişletiyor ve seçkin, profesyonel eğitim danışmanlık firmalarıyla uzun vadeli iş birlikleri kurmak istiyoruz.

Johnathan Academy'yi farklı kılan; güçlü akademik odağı, üniversiteye hazırlık programı ve öğrencilerin uzun vadeli başarısıdır.

Güçlü Üniversite Sonuçları
Eğitim ağımızda 2024–2026 mezunlarımız şu sonuçları elde etti:
{STATS}

Mezunlarımız ayrıca Imperial College London, King's College London, Edinburgh Üniversitesi, Melbourne Üniversitesi, Sidney Üniversitesi, Queen's University, Western University, Simon Fraser University ve daha birçok saygın kurumdan kabul aldı.

Neden Johnathan Academy?
• Vancouver'da 8–12. sınıf eğitimi
• British Columbia müfredatı ve Dogwood Diploması
• Güçlü akademik eğitim ve üniversiteye hazırlık
• AP dersleri ve ileri düzey akademik fırsatlar
• Kişiye özel akademik ve üniversite planlaması
• 12. sınıftan önce güçlü bir akademik geçmiş oluşturmak için Kanada'ya erken giriş

Öğrencileriniz ve aileleri, güçlü üniversite sonuçlarına sahip, akademik odaklı bir Kanada lisesi arıyorsa sizinle iş birliği yapmaktan memnuniyet duyarız.

Benimle 30 dakikalık bir çevrimiçi görüşme için buradan randevu alabilirsiniz:
{LINK}
Dilerseniz bu e-postayı doğrudan yanıtlayabilirsiniz.

Saygılarımla,
Polo Zhang
Johnathan Academy, Vancouver, Kanada""")

T["ka"] = ("ქართული", "პარტნიორობა ვანკუვერის სკოლასთან (8–12 კლასები) | 1 900-ზე მეტი უნივერსიტეტის შეთავაზება", f"""პატივცემულო {{name}},

მოგესალმებით ვანკუვერიდან, კანადა!

მე ვარ პოლო ჟანგი, Johnathan Academy-ის წარმომადგენელი. ჩვენი სკოლა არის ბრიტანეთის კოლუმბიის დამოუკიდებელი საშუალო სკოლა ვანკუვერში, რომელიც 8–12 კლასის მოსწავლეებს ემსახურება.

ამჟამად ვაფართოებთ ჩვენს საერთაშორისო ქსელს და გვსურს გრძელვადიანი თანამშრომლობა შერჩეულ პროფესიონალურ საგანმანათლებლო სააგენტოებთან.

Johnathan Academy-ს გამოარჩევს ძლიერი აკადემიური ფოკუსი, უნივერსიტეტისთვის მომზადება და მოსწავლეების გრძელვადიანი წარმატება.

უნივერსიტეტში ჩარიცხვის მაღალი შედეგები
ჩვენს საგანმანათლებლო ქსელში 2024–2026 წლების კურსდამთავრებულებმა მიაღწიეს:
{STATS}

ჩვენმა კურსდამთავრებულებმა ასევე მიიღეს შეთავაზებები Imperial College London-ისგან, King's College London-ისგან, ედინბურგის, მელბურნისა და სიდნეის უნივერსიტეტებისგან, Queen's University-ისგან, Western University-ისგან, Simon Fraser University-ისგან და სხვა წამყვანი უნივერსიტეტებისგან.

რატომ Johnathan Academy?
• 8–12 კლასების განათლება ვანკუვერში
• ბრიტანეთის კოლუმბიის სასწავლო პროგრამა და Dogwood დიპლომი
• ძლიერი აკადემიური და საუნივერსიტეტო მომზადება
• AP კურსები და დამატებითი აკადემიური შესაძლებლობები
• ინდივიდუალური აკადემიური და საუნივერსიტეტო დაგეგმვა
• კანადაში ადრე ჩამოსვლა, რათა მოსწავლემ მე-12 კლასამდე ძლიერი აკადემიური ისტორია შექმნას

თუ თქვენი მოსწავლეები და ოჯახები ეძებენ აკადემიურად ძლიერ კანადურ სკოლას, სიამოვნებით განვიხილავთ თქვენთან თანამშრომლობას.

30-წუთიანი ონლაინ შეხვედრის დასაჯავშნად:
{LINK}
ასევე შეგიძლიათ პირდაპირ უპასუხოთ ამ წერილს.

პატივისცემით,
პოლო ჟანგი
Johnathan Academy, ვანკუვერი, კანადა""")

T["hy"] = ("Հայերեն", "Համագործակցություն Վանկուվերի 8–12-րդ դասարանների դպրոցի հետ | Համալսարանների 1900+ առաջարկ", f"""Հարգելի {{name}},

Ողջույններ Վանկուվերից, Կանադա։

Ես Պոլո Ժանգն եմ՝ Johnathan Academy-ից։ Մեր դպրոցը Բրիտանական Կոլումբիայի անկախ միջնակարգ դպրոց է Վանկուվերում, որտեղ սովորում են 8–12-րդ դասարանների աշակերտներ։

Մենք ընդլայնում ենք մեր միջազգային ցանցը և ցանկանում ենք երկարաժամկետ համագործակցություն հաստատել ընտրված մասնագիտական կրթական գործակալությունների հետ։

Johnathan Academy-ին առանձնացնում են ակադեմիական ուժեղ կենտրոնացումը, համալսարանին նախապատրաստումը և աշակերտների երկարաժամկետ հաջողությունը։

Համալսարանական բարձր արդյունքներ
Մեր կրթական ցանցում 2024–2026 թվականների շրջանավարտները ունեցել են՝
{STATS}

Մեր շրջանավարտները առաջարկներ են ստացել նաև Imperial College London-ից, King's College London-ից, Էդինբուրգի, Մելբուռնի և Սիդնեյի համալսարաններից, Queen's University-ից, Western University-ից, Simon Fraser University-ից և այլ առաջատար հաստատություններից։

Ինչու՞ Johnathan Academy
• 8–12-րդ դասարանների կրթություն Վանկուվերում
• Բրիտանական Կոլումբիայի ուսումնական ծրագիր և Dogwood դիպլոմ
• Ուժեղ ակադեմիական և համալսարանական նախապատրաստում
• AP դասընթացներ և խորացված ակադեմիական հնարավորություններ
• Անհատական ակադեմիական և համալսարանական պլանավորում
• Կանադա ավելի վաղ ժամանում՝ 12-րդ դասարանից առաջ ուժեղ ակադեմիական արդյունքներ ձևավորելու համար

Եթե ձեր աշակերտներն ու ընտանիքները փնտրում են ակադեմիապես ուժեղ կանադական դպրոց, սիրով կքննարկենք համագործակցությունը ձեզ հետ։

30 րոպեանոց առցանց հանդիպում ամրագրելու համար՝
{LINK}
Կարող եք նաև ուղղակի պատասխանել այս նամակին։

Հարգանքով՝
Պոլո Ժանգ
Johnathan Academy, Վանկուվեր, Կանադա""")

T["th"] = ("ภาษาไทย", "ความร่วมมือกับโรงเรียนเกรด 8–12 ในแวนคูเวอร์ | ได้รับข้อเสนอจากมหาวิทยาลัยกว่า 1,900 แห่ง", f"""เรียน คุณ{{name}}

สวัสดีจากเมืองแวนคูเวอร์ ประเทศแคนาดา

ผมชื่อ Polo Zhang จาก Johnathan Academy โรงเรียนมัธยมเอกชนในรัฐบริติชโคลัมเบีย ตั้งอยู่ที่เมืองแวนคูเวอร์ เปิดสอนนักเรียนเกรด 8–12

ขณะนี้เรากำลังขยายเครือข่ายการรับนักเรียนต่างชาติ และต้องการสร้างความร่วมมือระยะยาวกับเอเจนซี่การศึกษามืออาชีพที่คัดเลือกแล้ว

จุดเด่นของ Johnathan Academy คือการเน้นวิชาการอย่างเข้มข้น การเตรียมความพร้อมเข้ามหาวิทยาลัย และความสำเร็จระยะยาวของนักเรียน

ผลลัพธ์การเข้ามหาวิทยาลัยที่โดดเด่น
ในเครือข่ายการศึกษาของเรา นักเรียนที่จบการศึกษาปี 2024–2026 มีผลงานดังนี้
{STATS}

ผู้สำเร็จการศึกษาของเรายังได้รับข้อเสนอจาก Imperial College London, King's College London, University of Edinburgh, University of Melbourne, University of Sydney, Queen's University, Western University, Simon Fraser University และสถาบันชั้นนำอื่น ๆ อีกมากมาย

ทำไมต้อง Johnathan Academy
• การศึกษาเกรด 8–12 ในแวนคูเวอร์
• หลักสูตรรัฐบริติชโคลัมเบียและประกาศนียบัตร Dogwood
• การเตรียมความพร้อมด้านวิชาการและการเข้ามหาวิทยาลัยอย่างเข้มแข็ง
• วิชา AP และโอกาสทางวิชาการขั้นสูง
• การวางแผนการเรียนและการเข้ามหาวิทยาลัยเป็นรายบุคคล
• เข้ามาเรียนในแคนาดาเร็วขึ้น เพื่อสร้างผลการเรียนที่แข็งแกร่งก่อนเกรด 12

หากนักเรียนและครอบครัวของท่านกำลังมองหาโรงเรียนมัธยมในแคนาดาที่เน้นวิชาการและมีผลลัพธ์การเข้ามหาวิทยาลัยที่ดี เรายินดีอย่างยิ่งที่จะหารือเรื่องความร่วมมือกับท่าน

ท่านสามารถนัดประชุมออนไลน์ 30 นาทีกับผมได้ที่นี่
{LINK}
หรือตอบกลับอีเมลนี้ได้โดยตรง

ขอแสดงความนับถือ
Polo Zhang
Johnathan Academy, แวนคูเวอร์ แคนาดา""")

T["vi"] = ("Tiếng Việt", "Hợp tác với trường Trung học lớp 8–12 tại Vancouver | Hơn 1.900 thư mời nhập học đại học", f"""Kính gửi {{name}},

Xin gửi lời chào từ Vancouver, Canada!

Tôi là Polo Zhang, đại diện Johnathan Academy – trường trung học tư thục độc lập thuộc tỉnh British Columbia, tọa lạc tại Vancouver, giảng dạy học sinh từ lớp 8 đến lớp 12.

Chúng tôi đang mở rộng mạng lưới tuyển sinh quốc tế và mong muốn xây dựng quan hệ hợp tác lâu dài với các công ty tư vấn du học chuyên nghiệp được chọn lọc.

Điểm khác biệt của Johnathan Academy là sự tập trung mạnh vào học thuật, chuẩn bị vào đại học và thành công lâu dài của học sinh.

Kết quả đại học nổi bật
Trong hệ thống giáo dục của chúng tôi, học sinh tốt nghiệp các năm 2024–2026 đạt được:
{STATS}

Học sinh của chúng tôi còn nhận được thư mời từ Imperial College London, King's College London, Đại học Edinburgh, Đại học Melbourne, Đại học Sydney, Queen's University, Western University, Simon Fraser University và nhiều trường danh tiếng khác.

Vì sao chọn Johnathan Academy?
• Chương trình lớp 8–12 tại Vancouver
• Chương trình học British Columbia và bằng Dogwood Diploma
• Nền tảng học thuật vững chắc và chuẩn bị vào đại học
• Các môn AP và cơ hội học thuật nâng cao
• Lập kế hoạch học tập và đại học cho từng học sinh
• Sang Canada sớm hơn để xây dựng hồ sơ học tập vững vàng trước lớp 12

Nếu học sinh và phụ huynh của quý công ty đang tìm một trường trung học Canada chú trọng học thuật và có kết quả đại học tốt, chúng tôi rất mong được hợp tác cùng quý vị.

Quý vị có thể đặt lịch họp trực tuyến 30 phút với tôi tại đây:
{LINK}
Hoặc trả lời trực tiếp email này.

Trân trọng,
Polo Zhang
Johnathan Academy, Vancouver, Canada""")

T["ko"] = ("한국어", "밴쿠버 8–12학년 사립학교 파트너십 제안 | 대학 합격 1,900건 이상", f"""{{name}} 님께,

캐나다 밴쿠버에서 인사드립니다.

저는 Johnathan Academy의 Polo Zhang입니다. 저희 학교는 밴쿠버에 위치한 브리티시컬럼비아주 인가 사립 중·고등학교로, 8학년부터 12학년까지의 학생을 교육하고 있습니다.

현재 저희는 국제 학생 모집 네트워크를 확대하고 있으며, 엄선된 전문 유학원과 장기적인 파트너십을 맺고자 합니다.

Johnathan Academy는 탄탄한 학업 중심 교육, 대학 진학 준비, 그리고 학생의 장기적인 성공에 집중한다는 점에서 차별화됩니다.

우수한 대학 진학 실적
저희 교육 네트워크의 2024–2026년 졸업생 실적:
{STATS}

졸업생들은 Imperial College London, King's College London, 에든버러대, 멜버른대, 시드니대, Queen's University, Western University, Simon Fraser University 등 여러 명문 대학으로부터도 합격 통보를 받았습니다.

왜 Johnathan Academy인가요?
• 밴쿠버에서의 8–12학년 교육
• BC주 정규 교육과정 및 Dogwood 졸업장
• 탄탄한 학업 및 대학 진학 준비
• AP 과목 및 심화 학업 기회
• 학생별 맞춤 학업·대학 진학 설계
• 12학년 이전에 캐나다에 일찍 와서 우수한 내신을 쌓을 수 있는 기회

학업 중심의 캐나다 고등학교를 찾는 학생과 학부모님이 계시다면, 귀사와의 협력을 기쁘게 논의하고 싶습니다.

아래 링크에서 30분 온라인 미팅을 예약하실 수 있습니다.
{LINK}
이 이메일에 바로 회신하셔도 됩니다.

감사합니다.
Polo Zhang
Johnathan Academy, 캐나다 밴쿠버""")

T["ja"] = ("日本語", "バンクーバーの8〜12年生向け私立校とのパートナーシップ｜大学合格1,900件以上", f"""{{name}} 様

カナダ・バンクーバーよりご挨拶申し上げます。

Johnathan Academy の Polo Zhang と申します。当校はバンクーバーにあるブリティッシュコロンビア州認定の私立中等学校で、8年生から12年生までの生徒を受け入れております。

現在、当校では海外での留学生募集ネットワークを拡大しており、信頼できる留学エージェント様との長期的なパートナーシップを築きたいと考えております。

Johnathan Academy の特長は、学業重視の教育、大学進学に向けた準備、そして生徒の長期的な成功に力を入れている点です。

優れた大学進学実績
当校の教育ネットワークにおける2024〜2026年卒業生の実績：
{STATS}

卒業生は Imperial College London、King's College London、エディンバラ大学、メルボルン大学、シドニー大学、Queen's University、Western University、Simon Fraser University など、多くの名門大学からも合格を得ています。

Johnathan Academy の特長
• バンクーバーでの8〜12年生の教育
• BC州カリキュラムと Dogwood Diploma（州卒業資格）
• 充実した学業指導と大学進学準備
• AP科目および発展的な学習機会
• 一人ひとりに合わせた学習・進学計画
• 12年生より前にカナダへ来ることで、しっかりとした成績を築けること

学業重視で大学進学実績の高いカナダの中等学校をお探しの生徒様・ご家族様がいらっしゃいましたら、ぜひ貴社との提携についてお話しさせていただければ幸いです。

30分のオンラインミーティングはこちらからご予約いただけます：
{LINK}
本メールへの直接のご返信も歓迎いたします。

何卒よろしくお願い申し上げます。
Polo Zhang
Johnathan Academy（カナダ・バンクーバー）""")

T["it"] = ("Italiano", "Partnership con una scuola per i gradi 8–12 a Vancouver | Oltre 1.900 ammissioni universitarie", f"""Gentile {{name}},

un cordiale saluto da Vancouver, Canada!

Mi chiamo Polo Zhang e rappresento la Johnathan Academy, una scuola secondaria indipendente della British Columbia con sede a Vancouver, per studenti dal grado 8 al grado 12.

Stiamo ampliando la nostra rete internazionale di reclutamento e cerchiamo collaborazioni a lungo termine con agenzie educative professionali selezionate.

La Johnathan Academy si distingue per una forte impostazione accademica, una preparazione mirata all'università e l'attenzione al successo degli studenti nel lungo periodo.

Ottimi risultati di ammissione universitaria
Nella nostra rete di scuole, i diplomati 2024–2026 hanno ottenuto:
{STATS}

I nostri diplomati hanno ricevuto offerte anche da Imperial College London, King's College London, University of Edinburgh, University of Melbourne, University of Sydney, Queen's University, Western University, Simon Fraser University e molte altre università prestigiose.

Perché la Johnathan Academy?
• Gradi 8–12 a Vancouver
• Programma della British Columbia e Dogwood Diploma
• Solida formazione accademica e preparazione universitaria
• Corsi AP e percorsi accademici avanzati
• Pianificazione personalizzata dello studio e dell'università
• Arrivo anticipato in Canada per costruire un profilo accademico solido prima del grado 12

Se i vostri studenti e le loro famiglie cercano una scuola secondaria canadese con un forte orientamento accademico e ottimi risultati universitari, saremmo lieti di collaborare con voi.

Può prenotare una videochiamata di 30 minuti con me qui:
{LINK}
Oppure può rispondere direttamente a questa e-mail.

Cordiali saluti
Polo Zhang
Johnathan Academy, Vancouver, Canada""")

TRANSLATIONS = {k: {"label": v[0], "subject": v[1], "body": v[2]} for k, v in T.items()}

UNSUBSCRIBE = ("\n\n—\nJohnathan Academy · 400-5750 Oak Street, Vancouver BC V6M 2V9, Canada\n"
               "If you would prefer not to receive further emails from us, simply reply \"unsubscribe\".")


def lang_for(country):
    return COUNTRY_LANG.get((country or "").strip())


def compose(prospect, english=None, translation=None):
    """拼出一封开发邮件：英文在上，当地语言版本在下。返回 (subject, body, lang)。"""
    english = english or EN
    name = prospect.get("contact") if prospect.get("contact") and "General" not in prospect.get("contact", "") \
        else prospect.get("agency", "Education Partner")
    lang = lang_for(prospect.get("country"))
    agency = prospect.get("agency") or "your agency"
    body = english["body"].replace("{name}", name).replace("{agency}", agency)
    subject = english["subject"]
    tr = TRANSLATIONS.get(lang) if translation is None else translation  # False = 只发英文
    if tr:
        body += f"\n\n———— {tr['label']} ————\n\n" + tr["body"].replace("{name}", name).replace("{agency}", agency)
    return subject, body + UNSUBSCRIBE, lang


# ---------- 跟进邮件（第一封发出 7 天没回复时用） ----------
FOLLOWUP = {"label": "English", "subject": "Following up – Johnathan Academy partnership (Vancouver, Grades 8–12)",
            "body": f"""Dear {{name}},

I wanted to follow up on my previous email about a partnership with Johnathan Academy, an academically focused Grade 8–12 school in Vancouver, Canada (362 graduates, 1,900+ university offers in 2024–2026).

If you work with families looking for Canadian high schools, I would be glad to introduce our programs, admissions process and agency terms in a short online call:
{LINK}

Or simply reply to this email with a convenient time.

Warm regards,
Polo Zhang
Johnathan Academy, Vancouver, Canada"""}

_FU = {
    "es": "Estimado/a {name}:\n\nLe escribo para dar seguimiento a mi correo anterior sobre una colaboración con Johnathan Academy, un colegio de Grado 8 a 12 con enfoque académico en Vancouver, Canadá (362 graduados y más de 1.900 admisiones universitarias en 2024–2026).\n\nSi trabaja con familias que buscan colegios de secundaria en Canadá, con gusto le presentaré nuestros programas, el proceso de admisión y las condiciones para agencias en una breve llamada en línea:\n{link}\n\nO simplemente responda a este correo con un horario que le convenga.\n\nSaludos cordiales,\nPolo Zhang",
    "pt": "Prezado(a) {name},\n\nEscrevo para dar seguimento ao meu e-mail anterior sobre uma parceria com a Johnathan Academy, uma escola de 8º ao 12º ano com foco acadêmico em Vancouver, Canadá (362 formandos e mais de 1.900 aprovações universitárias em 2024–2026).\n\nSe você trabalha com famílias que procuram escolas de ensino médio no Canadá, terei prazer em apresentar nossos programas, o processo de admissão e as condições para agências em uma breve chamada online:\n{link}\n\nOu simplesmente responda a este e-mail com um horário conveniente.\n\nAtenciosamente,\nPolo Zhang",
    "cs": "Vážená paní / vážený pane {name},\n\ndovoluji si navázat na svůj předchozí e-mail ohledně spolupráce s Johnathan Academy, akademicky zaměřenou střední školou (Grade 8–12) ve Vancouveru v Kanadě (362 absolventů a více než 1 900 přijetí na univerzity v letech 2024–2026).\n\nPokud pracujete s rodinami, které hledají střední školu v Kanadě, rád vám v krátkém online hovoru představím naše programy, přijímací proces a podmínky pro agentury:\n{link}\n\nNebo mi jednoduše odpovězte s termínem, který vám vyhovuje.\n\nS pozdravem\nPolo Zhang",
    "sk": "Vážená pani / vážený pán {name},\n\ndovoľujem si nadviazať na môj predchádzajúci e-mail o spolupráci s Johnathan Academy, akademicky zameranou strednou školou (Grade 8–12) vo Vancouveri v Kanade (362 absolventov a viac ako 1 900 prijatí na univerzity v rokoch 2024–2026).\n\nAk pracujete s rodinami, ktoré hľadajú strednú školu v Kanade, rád vám v krátkom online hovore predstavím naše programy, prijímací proces a podmienky pre agentúry:\n{link}\n\nAlebo mi jednoducho odpíšte s termínom, ktorý vám vyhovuje.\n\nS pozdravom\nPolo Zhang",
    "pl": "Szanowni Państwo / {name},\n\nchciałbym nawiązać do mojej poprzedniej wiadomości w sprawie współpracy z Johnathan Academy – szkołą średnią (klasy 8–12) o profilu akademickim w Vancouver w Kanadzie (362 absolwentów i ponad 1900 przyjęć na uniwersytety w latach 2024–2026).\n\nJeśli pracują Państwo z rodzinami szukającymi szkoły średniej w Kanadzie, chętnie przedstawię nasze programy, proces rekrutacji i warunki współpracy dla agencji podczas krótkiej rozmowy online:\n{link}\n\nMożna też po prostu odpowiedzieć na tę wiadomość, podając dogodny termin.\n\nZ wyrazami szacunku\nPolo Zhang",
    "hu": "Kedves {name}!\n\nKorábbi levelemre szeretnék visszatérni a Johnathan Academy-vel való együttműködés ügyében. Iskolánk akadémiai fókuszú, 8–12. évfolyamos középiskola Vancouverben, Kanadában (362 végzős és több mint 1900 egyetemi felvétel 2024–2026 között).\n\nHa olyan családokkal dolgozik, akik kanadai középiskolát keresnek, szívesen bemutatom programjainkat, a felvételi folyamatot és az ügynökségi feltételeket egy rövid online megbeszélésen:\n{link}\n\nVagy egyszerűen válaszoljon erre a levélre egy Önnek megfelelő időponttal.\n\nÜdvözlettel:\nPolo Zhang",
    "de": "Sehr geehrte Damen und Herren / {name},\n\nich möchte an meine vorherige E-Mail zu einer Partnerschaft mit der Johnathan Academy anknüpfen, einer akademisch ausgerichteten Schule für die Klassen 8–12 in Vancouver, Kanada (362 Absolventen und über 1.900 Studienplatzzusagen in 2024–2026).\n\nWenn Sie mit Familien arbeiten, die eine High School in Kanada suchen, stelle ich Ihnen gern unsere Programme, das Aufnahmeverfahren und die Konditionen für Agenturen in einem kurzen Online-Gespräch vor:\n{link}\n\nOder antworten Sie einfach auf diese E-Mail mit einem passenden Termin.\n\nMit freundlichen Grüßen\nPolo Zhang",
    "tr": "Sayın {name},\n\nVancouver, Kanada'da akademik odaklı bir 8–12. sınıf okulu olan Johnathan Academy ile iş birliği konusundaki önceki e-postamı takip etmek istedim (2024–2026 döneminde 362 mezun ve 1.900'den fazla üniversite kabulü).\n\nKanada'da lise arayan ailelerle çalışıyorsanız, programlarımızı, kabul sürecimizi ve acente koşullarımızı kısa bir çevrim içi görüşmede memnuniyetle tanıtırım:\n{link}\n\nYa da size uygun bir zamanı belirterek bu e-postayı yanıtlamanız yeterli.\n\nSaygılarımla,\nPolo Zhang",
    "ka": "პატივცემულო {name},\n\nმსურს გავაგრძელო ჩემი წინა წერილი Johnathan Academy-სთან თანამშრომლობის შესახებ. ეს არის აკადემიურად ორიენტირებული სკოლა (8–12 კლასები) ვანკუვერში, კანადა (362 კურსდამთავრებული და 1 900-ზე მეტი უნივერსიტეტში მიღება 2024–2026 წლებში).\n\nთუ მუშაობთ ოჯახებთან, რომლებიც კანადაში საშუალო სკოლას ეძებენ, სიამოვნებით გაგაცნობთ ჩვენს პროგრამებს, მიღების პროცესს და სააგენტო პირობებს მოკლე ონლაინ შეხვედრაზე:\n{link}\n\nან უბრალოდ უპასუხეთ ამ წერილს თქვენთვის მოსახერხებელი დროით.\n\nპატივისცემით,\nPolo Zhang",
    "hy": "Հարգելի {name},\n\nՑանկանում եմ շարունակել իմ նախորդ նամակը Johnathan Academy-ի հետ համագործակցության վերաբերյալ։ Մենք ակադեմիական ուղղվածությամբ դպրոց ենք (8–12-րդ դասարաններ) Վանկուվերում, Կանադա (362 շրջանավարտ և 1900-ից ավելի համալսարանական ընդունելություն 2024–2026 թթ.)։\n\nԵթե աշխատում եք ընտանիքների հետ, որոնք Կանադայում ավագ դպրոց են փնտրում, սիրով կներկայացնեմ մեր ծրագրերը, ընդունելության գործընթացը և գործակալությունների պայմանները կարճ առցանց զրույցի ընթացքում՝\n{link}\n\nԿամ պարզապես պատասխանեք այս նամակին՝ նշելով ձեզ հարմար ժամը։\n\nՀարգանքով՝\nPolo Zhang",
    "th": "เรียน คุณ{name}\n\nขออนุญาตติดตามอีเมลฉบับก่อนเรื่องความร่วมมือกับ Johnathan Academy โรงเรียนเกรด 8–12 ที่เน้นวิชาการในเมืองแวนคูเวอร์ ประเทศแคนาดา (ผู้สำเร็จการศึกษา 362 คน และได้รับการตอบรับจากมหาวิทยาลัยกว่า 1,900 แห่งในปี 2024–2026)\n\nหากท่านทำงานกับครอบครัวที่กำลังมองหาโรงเรียนมัธยมในแคนาดา ผมยินดีแนะนำหลักสูตร ขั้นตอนการรับสมัคร และเงื่อนไขสำหรับเอเจนซี่ผ่านการประชุมออนไลน์สั้น ๆ:\n{link}\n\nหรือตอบกลับอีเมลนี้พร้อมแจ้งเวลาที่สะดวกได้เลยครับ\n\nด้วยความเคารพ\nPolo Zhang",
    "vi": "Kính gửi {name},\n\nTôi xin phép tiếp nối email trước về việc hợp tác với Johnathan Academy, trường trung học (lớp 8–12) chú trọng học thuật tại Vancouver, Canada (362 học sinh tốt nghiệp và hơn 1.900 thư mời nhập học đại học trong giai đoạn 2024–2026).\n\nNếu quý vị đang làm việc với các gia đình tìm trường trung học tại Canada, tôi rất sẵn lòng giới thiệu chương trình, quy trình tuyển sinh và điều kiện hợp tác dành cho đại lý trong một cuộc gọi trực tuyến ngắn:\n{link}\n\nHoặc quý vị chỉ cần trả lời email này với thời gian thuận tiện.\n\nTrân trọng,\nPolo Zhang",
    "ko": "{name}님께,\n\n캐나다 밴쿠버의 학업 중심 8–12학년 학교인 Johnathan Academy와의 파트너십에 관해 지난번 보내드린 메일에 이어 연락드립니다(2024–2026년 졸업생 362명, 대학 합격 1,900건 이상).\n\n캐나다 고등학교를 찾는 가정과 함께 일하고 계시다면, 짧은 온라인 미팅에서 저희 프로그램과 입학 절차, 에이전시 조건을 기꺼이 소개해 드리겠습니다:\n{link}\n\n또는 편하신 시간을 적어 이 메일에 회신해 주셔도 됩니다.\n\n감사합니다.\nPolo Zhang 드림",
    "ja": "{name} 様\n\n先日お送りした、カナダ・バンクーバーの進学重視の8〜12年生向けスクール、Johnathan Academy との提携に関するメールのフォローアップでご連絡いたしました（2024〜2026年の卒業生362名、大学合格1,900件以上）。\n\nカナダの高校をお探しのご家庭とお仕事をされている場合、短いオンライン面談にて当校のプログラム、出願手続き、エージェント条件をご紹介できれば幸いです：\n{link}\n\nご都合のよい日時をこのメールにご返信いただくだけでも結構です。\n\nよろしくお願いいたします。\nPolo Zhang",
    "it": "Gentile {name},\n\nle scrivo per dare seguito alla mia e-mail precedente su una possibile partnership con la Johnathan Academy, una scuola a forte orientamento accademico per i gradi 8–12 a Vancouver, Canada (362 diplomati e oltre 1.900 ammissioni universitarie nel 2024–2026).\n\nSe lavorate con famiglie che cercano una scuola superiore in Canada, sarò lieto di presentarvi i nostri programmi, la procedura di ammissione e le condizioni per le agenzie in una breve videochiamata:\n{link}\n\nOppure risponda semplicemente a questa e-mail indicando un orario comodo.\n\nCordiali saluti\nPolo Zhang",
}
FOLLOWUP_TRANSLATIONS = {k: {"label": TRANSLATIONS[k]["label"], "subject": "", "body": v.replace("{link}", LINK)}
                         for k, v in _FU.items()}


# ---------- 新版第一封开发邮件（2026-10，突出代理的好处；译文待英文定稿后生成） ----------
EN_V2 = {"label": "English",
         "subject": "Partnership invitation – Vancouver Grade 8–12 school | 1,900+ university offers | multi-year commission",
         "body": f"""Dear {{name}},

I'm Polo Zhang from Johnathan Academy, a BC Ministry of Education certified independent high school (Grades 8–12) on Vancouver's West Side. I came across {{agency}} and believe our school could be a strong fit for the families you advise.

RESULTS FAMILIES ASK ABOUT
Across our school network, the 2024–2026 graduating classes earned 1,900+ university offers – about 5.3 per graduate – including the University of Toronto (242), UBC (125), McMaster (57), Waterloo (39), McGill (37) and UCL (34).

WHY FAMILIES CHOOSE US
• Academic focus: small classes taught by BC-certified teachers, with individual course and university planning from day one
• BC Dogwood Diploma, plus AP courses – we are an official AP and SAT test centre, and a test centre for international math, physics and chemistry competitions
• Entry from Grade 8, so students build English and a strong transcript before Grade 12
• Safe, central location near SkyTrain, 15 minutes from YVR, with screened homestay families

WHY AGENCIES LIKE WORKING WITH US
• Multi-year commission: 20–30% of first-year tuition, plus commission in Years 2 and 3
• A direct line to me for fast admissions answers, and clear commission statements every term
• Canada's international student cap does not apply to K-12 students, so high school remains an open, stable pathway to Canadian universities

NEXT STEP
Book a 30-minute call at a time that suits you: {LINK}
Or simply reply "INFO" and I'll send our agency kit: brochure, tuition and fees, admissions steps and commission terms.

I look forward to hearing from you.

Warm regards,
Polo Zhang
Johnathan Academy | 5750 Oak Street, Vancouver, BC, Canada
https://johnathana.ca"""}

# 系统第一次打开时放进「邮件模板」的默认模板；之后在网页里改
DEFAULT_TEMPLATES = [
    {"name": "开发邮件 · 新版（推荐）", "kind": "outreach", "subject": EN_V2["subject"], "body": EN_V2["body"],
     "translations": {}},
    {"name": "开发邮件 · 短版（原有）", "kind": "outreach", "subject": EN["subject"], "body": EN["body"],
     "translations": {k: v["body"] for k, v in TRANSLATIONS.items()}},
    {"name": "跟进邮件", "kind": "followup", "subject": FOLLOWUP["subject"], "body": FOLLOWUP["body"],
     "translations": {k: v["body"] for k, v in FOLLOWUP_TRANSLATIONS.items()}},
]
