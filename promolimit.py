import praw
import configparser
import pandas
import re
import googleapiclient.discovery
import googleapiclient.errors
from google.oauth2 import service_account

try:
    service_key_file = 'service_key.json'
    credentials = service_account.Credentials.from_service_account_file(service_key_file)
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
except:
    service_key_file = '/home/ubuntu/reddit/service_key.json'
    credentials = service_account.Credentials.from_service_account_file(service_key_file)
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
    
config = configparser.ConfigParser()   
try:
    config_path = 'autopolicjant-dev.ini'
    config.read(config_path)
    client_id = config['reddit']['client_id']
except:
    config_path = '/home/ubuntu/reddit/autopolicjant.ini'
    config.read(config_path)


reddit = praw.Reddit(client_id=config['reddit']['client_id'],
                     client_secret=config['reddit']['client_secret'],
                     user_agent=config['reddit']['user_agent'],
                     password=config['reddit']['password'],
                     username=config['reddit']['username'])

monitored_sub = 'Polska'

promo_message = 'Twój post został usunięty automatycznie z następującego powodu:\n\n' \
    '**[Ograniczenie promocji](https://www.reddit.com/r/Polska/wiki/rules/#wiki_.A7_2._ograniczenie_promocji)**\n\n' \
    '* Pozwalamy na promocję ze strony stałych i aktywnych członków naszej społeczności, która nie przekracza 10% aktywności na /r/Polska.\n\n' \
    'Jeśli uważasz, że został on niesłusznie usunięty, [skontakuj się z moderatorami](https://reddit.com/message/compose/?to=/r/polska), a w treści dodaj link do usuniętej rzeczy.'

promoters = {
    'sample_user': ['site1.pl', 'site2.pl'],
    }

activity_table = pandas.DataFrame(columns=('id','time','promo'))

def get_yt_details(yt_id):
    try:
        request = youtube.videos().list(part="snippet,statistics", id=yt_id)
        details = request.execute()
        details = details["items"][0]
        details = {
            'title': details["snippet"]["title"],
            'channel': (details["snippet"]["channelTitle"]).lower(),
            'description': details["snippet"]["description"],
        }
        return details
    except Exception as zonk:
        print(f"Error while getting {yt_id} Youtube video details: {zonk}")

def check_yt(submission):
    try:
        youtube_id = re.search('(?:v=|.be/|shorts/|embed/)(.{11})', submission.url)
        for match in youtube_id.groups():
            if match is not None:
                youtube_id = match
                channel = get_yt_details(youtube_id)['channel']
                return channel
        return 'youtube'
    except Exception as zonk:
        print(f"Error while doing Youtube check on submission {submission.id}: {zonk}")

def check_promo(submission):
    for url in promoters[submission.author.name]:
        if submission.url.find(url) > 0:
            return True
    for url in promoters[submission.author.name]:
        if submission.selftext.find(url+'.pl') > 0:
            return True

for submission in reddit.subreddit(monitored_sub).stream.submissions(skip_existing=True):
    if submission.author.name in promoters:
        if check_promo(submission):
            activity_table = activity_table[0:0]
            for comment in submission.author.comments.new(limit=300):
                activity_check = False
                if comment.author == comment.submission.author and comment.submission.subreddit.display_name == monitored_sub:
                    if check_promo(comment.submission) or check_yt(comment.submission):
                        activity_check = True
                elif comment.submission.subreddit.display_name == monitored_sub:
                    for url in promoters[comment.author.name]:
                        if comment.body.find(url) > 0:
                            activity_check = True                     
                if (comment.score > -1 or len(comment.body) > 15 or activity_check):
                    activity_table = activity_table.append({'id': comment.id, 'time': comment.created_utc, 'promo': activity_check}, ignore_index=True)
            for post in submission.author.submissions.new(limit=100):
                activity_check = False
                if post.subreddit.display_name == monitored_sub:
                    if check_promo(post) or check_yt(post):
                        activity_check = True
                if post.is_robot_indexable and (post.score > 0 or activity_check):
                    activity_table = activity_table.append({'id': post.id, 'time': post.created_utc, 'promo': activity_check}, ignore_index=True)
            activity_table = activity_table.sort_values(by='time', ascending=False)
            activity_table = activity_table.head(100)

            if activity_table['promo'].mean() > 0.15:
                submission.mod.remove()
                submission.mod.send_removal_message(promo_message, type='public')
            
    