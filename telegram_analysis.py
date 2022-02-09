#for extraction
from telethon import TelegramClient
from telethon.tl import functions as f, types as t
import configparser
import asyncio
import os
#for analysis
import pandas as pd
import numpy as np
import emoji
import seaborn as sns
import matplotlib.pyplot as plt
from wordcloud import WordCloud
#for export
from fpdf import FPDF
import glob

#1. Establish connection
try:
    config = configparser.ConfigParser()
    config.read("config.ini")
    api_id = config["Telegram"]["api_id"]
    api_hash = config["Telegram"]["api_hash"]
    client = TelegramClient("session", api_id, api_hash)
    client.start()
except Exception as e:
    print(e)
    exit(1)

#1.1 Get messages
messages = []
id = input("Enter friend's Telegram handle without @ or their phone number (with country code): ").strip()
name = input("Enter friend's name to display on report: ").strip()
extract_limit = int(input("Number of messages to extract (set 0 to analyze all, minimum 100): "))

async def main():
    global messages
    offset_id = 0
    limit = 100
    total_msgs = 0

    try:
        chat = await client.get_entity(id)
    except Exception as e:
        print("ID or phone could not be found in your conversations, please try again")
        exit(1)

    print("Extracting messages, this may take some time...")
    while True:
        history = await client(f.messages.GetHistoryRequest(
        peer=chat,
        offset_id=offset_id,
        offset_date=None,
        add_offset=0,
        limit=limit,
        max_id=0,
        min_id=0,
        hash=0
    ))
        if not history.messages:
            break
        msgs = history.messages

        for msg in msgs:
            messages.append(msg.to_dict())

        offset_id = msgs[len(msgs) - 1].id

        total_msgs += len(msgs)
        if extract_limit != 0 and total_msgs >= extract_limit:
            messages = messages[:extract_limit]
            break

        '''
        await client.log_out()
        '''

with client:
    client.loop.run_until_complete(main())

print("Extraction complete! Analyzing...")


#2. Parse messages
parsed_messages = []
last_date = np.nan
last_sender = np.nan

for i in messages[::-1]:

    try:
        message = i['message']
    except:
        message = np.nan

    try:
        sender = i['from_id']['user_id']
        sender = 'You'
    except:
        sender = name

    try:
        date = i['date']
    except:
        date = last_date

    parsed_messages.append({"Sender" :sender, "Date" : date, "Message" : message})

    last_sender = sender
    last_date = date


#3. Analyze

def extract_emojis(text):
    emojis = {emoji.demojize(c,delimiters=('','')) for c in text if c in emoji.UNICODE_EMOJI['en']}
    if emojis:
        emojis = {emoji for emoji in emojis if "skin" not in emoji}
        emojis = ','.join(emojis).replace("_"," ")
        return emojis
    else:
        return np.nan

df = pd.DataFrame(parsed_messages)
df["Date"] = pd.to_datetime(df["Date"])
df["Msg_len"] = df["Message"].str.len()
df["Lag"] = df["Date"] - df['Date'].shift(1)
df.Lag = round(df.Lag.dt.seconds/60,2)

df['Emoji'] = df['Message'].apply(lambda x: extract_emojis(x) if type(x) == str else np.nan)
emojis = df[df.Emoji.notna()].groupby(['Sender','Emoji']).agg(Occurences=("Emoji", "size")).reset_index()
friend_top10 = emojis[emojis.Sender == "You"][['Occurences','Emoji']].nlargest(10, "Occurences")
you_top10 = emojis[emojis.Sender == name][['Occurences','Emoji']].nlargest(10, "Occurences")

response_delays = df[(df.Lag < 30) & (df.Sender != df.Sender.shift(1))][["Sender",'Lag']]
avg_delay_response = round(response_delays.groupby("Sender").Lag.mean(),2)

avg_msg_len = df.groupby("Sender").Msg_len.mean().astype(int)
total_msgs = df['Sender'].value_counts()

conv_init = df[df.Lag > 600].groupby("Sender").Message.count()

#graphs
plt.figure(figsize=(3,2))
ax = plt.axes()

ax.set_ylim(0,300)
sns.boxplot(x='Sender', y='Msg_len', data=df)
plt.tight_layout()
ax.set_ylabel("Characters/Message")
plt.savefig("avg_msg_len_plot.png")

ax.set_ylim(0,6)
sns.boxplot(x='Sender', y='Lag', data=response_delays)
plt.tight_layout()
ax.set_ylabel("Delay")
plt.savefig("avg_delay_plot.png")
plt.clf()

#word cloud
with open("STOP_WORDS.txt", 'r') as file:
    STOP_WORDS = {word.strip('\n') for word in file.readlines()}

you_msgs = df[df["Sender"] == 'You'].Message.dropna()
you_words = " ".join(you_msgs.to_list())
you_cloud = WordCloud(width=300,height=300,background_color='White',stopwords=STOP_WORDS, min_word_length=4, max_words=50).generate(you_words)
plt.imshow(you_cloud, interpolation='bilinear')
plt.axis("off")
you_cloud.to_file("Your_words.png")

friend_msgs = df[df["Sender"] == name].Message.dropna()
friend_words = " ".join(friend_msgs.to_list())
friend_cloud = WordCloud(width=300,height=300,background_color='White',stopwords=STOP_WORDS, min_word_length=4, max_words=50).generate(friend_words)
plt.imshow(friend_cloud, interpolation='bilinear')
plt.axis("off")
friend_cloud.to_file(name + "_words.png")

#4. Convert to PDF
print("Generating PDF...")
pdf = FPDF()
pdf.add_font('DejaVu','','resources/DejaVuSansCondensed.ttf',uni=True)

pdf.add_page() #summary stats page

pdf.set_font('DejaVu','', 24)
pdf.cell(80)
pdf.cell(40, 10, txt='Your Conversation with ' + name.capitalize() + ' Analyzed', align='C') #title
pdf.ln()

pdf.set_font('DejaVu', '', 12)
pdf.multi_cell(w=0,h=5,txt="Total number of messages:")
pdf.multi_cell(w=0,h=5,txt=total_msgs.to_string())
pdf.ln()

pdf.multi_cell(w=0,h=5,txt="Mean message length (characters):")
pdf.multi_cell(w=0,h=5,txt=avg_msg_len.to_string())
pdf.ln()
pdf.image("avg_msg_len_plot.png")
pdf.ln()

pdf.multi_cell(w=0,h=5,txt="Mean delay in response (minutes):")
pdf.multi_cell(w=0,h=5,txt=avg_delay_response.to_string())
pdf.ln()
pdf.image("avg_delay_plot.png")
pdf.ln()

pdf.multi_cell(w=0,h=5,txt="Conversations initiated (10+ hours after last msg):")
pdf.multi_cell(w=0,h=5,txt=conv_init.to_string())
pdf.ln(10)

pdf.add_page() #emoji page

pdf.set_font("DejaVu",'',16)
pdf.multi_cell(w=0,h=5,txt="Top 10 emojis that "+ name + " uses:")
pdf.ln()
pdf.set_font("DejaVu",'',12)
pdf.multi_cell(w=0,h=5,txt=friend_top10.to_string(index=False))
pdf.ln()

pdf.set_font("DejaVu",'',16)
pdf.multi_cell(w=0,h=5,txt="Top 10 emojis that you use:")
pdf.ln()
pdf.set_font("DejaVu",'',12)
pdf.multi_cell(w=0,h=5,txt=you_top10.to_string(index=False))
pdf.ln()

pdf.add_page() #word cloud page

pdf.set_font("DejaVu",'',16)
pdf.cell(80)
pdf.cell(40,10,txt="Your word cloud", align='C')
pdf.ln()
pdf.image("Your_words.png")
pdf.ln(10)

pdf.cell(80)
pdf.cell(40,10,txt=name + "'s word cloud", align='C')
pdf.ln()
pdf.image(name + "_words.png")


#5. Save PDF and Dataframe
if not os.path.exists('reports'):
    os.mkdir('reports')

file_name = name+'_'+"conversation_analysis"
pdf.output('reports/'+file_name+'.pdf')
print("PDF saved.")

df.to_csv('reports/'+file_name+'.csv')
print("CSV saved.")

#+ delete unneeded files
for file in glob.glob('*.png'):
    os.remove(file)

print("Goodbye!")
