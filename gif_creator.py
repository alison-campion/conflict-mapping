import os
import bisect
import branca
import datetime
import geopandas as gpd
import imageio
import IPython
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd
import requests
import shutil
import time
import urllib

from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver

import folium
from folium import plugins

from bs4 import BeautifulSoup
from dateutil import rrule
from IPython.display import display, HTML
from shapely.geometry import Point

# Set home directory
HOME_DIR = os.getcwd()

# Scrape ACLED Data
url = "https://www.acleddata.com/curated-data-files/"
page = requests.get(url)
soup = BeautifulSoup(page.content, "html.parser")
download = soup.find_all("a", class_="download-button")[0]
data_url = download.get("href")
data_filepath = os.path.join(HOME_DIR, "data")
os.makedirs(data_filepath, exist_ok=True)
data_download = urllib.request.urlretrieve(data_url, os.path.join(data_filepath, "acled_data.xlsx"))

# Read in the ACLED data and convert to shapefile
acled_data = pd.read_excel(os.path.join(data_filepath, "acled_data.xlsx"))
df_eth = acled_data[acled_data['COUNTRY'] == 'Ethiopia'].copy()
df_eth['geometry'] = df_eth.apply(lambda x: Point((float(x.LONGITUDE), float(x.LATITUDE))), axis=1)
df_eth = gpd.GeoDataFrame(df_eth, geometry='geometry').reset_index(drop=True)

# Read in admin boundareis
admin_df = gpd.read_file(os.path.join(data_filepath, 'ethiopia/ethiopia.shp'))
admin0_df = admin_df.dissolve(by='COUNTRY').reset_index()
poly = gpd.GeoSeries(admin0_df.loc[0,'geometry'])
center_loc = [poly.representative_point()[0].y, poly.representative_point()[0].x]
month_list = [dt for dt in rrule.rrule(rrule.MONTHLY,
                                       dtstart=datetime.datetime(1998, 1, 1, 0, 0),
                                       until=datetime.datetime.today())]

# Define data sorting and plotting functions
def get_incidents_by_month(df, month, month_list=month_list, geojson_flg=False):
    ind = month_list.index(month)
    date = month.__str__().split(' ')[0]+'T'+month.__str__().split(' ')[1]
    df_month = df.loc[(df['EVENT_DATE'] > month_list[ind]) &
                      (df['EVENT_DATE'] < month_list[ind + 1])]
    if geojson_flg is True:
        try:
            geojson_month = df_month.__geo_interface__
            geojson_month['features'][0]['properties']['dates'] = date
        except ValueError:
            geojson_month = {'features': {'dates' : date}}
        return geojson_month['features']
    else:
        return df_month

def generate_map(df, month, zoom_start=6, center_loc=center_loc):
    m = folium.Map(location=center_loc,
                            zoom_start=5,
                            tiles="Mapbox Control Room",
                            width="100%")

    # for each row in the data, add a cicle marker
    for index, row in df.iterrows():

        num_fatalities = row["FATALITIES"]

        popup_text = """
            <h4> {} </h4>
            <p><i> {} </i></p>
            <p> {} </p>
            <p style="color:#af0f00"><i> {} fatalities </i></p>
            """
        notes = row['NOTES']
        if type(notes) is float:
            notes = ''
        elif ':' in notes:
            notes = notes.split(':')[1]
        date = row['EVENT_DATE'].to_pydatetime().strftime('%d %b, %Y')
        popup_text = popup_text.format(row['EVENT_TYPE'], date, notes, row['FATALITIES'])

        iframe = branca.element.IFrame(html=popup_text, width=250, height=200)
        popup = folium.Popup(iframe, max_width=250)

        # radius of circles
        bins = [0, 1, 5, 10, 20, 30, 50, 75, 100, 150, 200, 500, 1000, 2000]
        radius =  (bisect.bisect(bins, num_fatalities)**2)/1.5
        if radius == 0:
            radius = 3
        
        if row['EVENT_TYPE'] == 'Violence against civilians':
            color = '#fc3535'
        elif row['EVENT_TYPE'] == 'Riots/Protests':
            color = '#b903bf'
        else:
            color="#f79f25"

        # add marker to the map
        folium.CircleMarker(location=(row["LATITUDE"],
                                      row["LONGITUDE"]),
                            radius=radius,
                            color=color,
                            popup=popup,
                            fill=True).add_to(m)
    return m

# Defin extent of gif
year_from = "Jan 2015"
year_until = "Feb 2019"
time_extent = month_list[month_list.index(datetime.datetime.strptime(year_from, '%b %Y')):
                         month_list.index(datetime.datetime.strptime(year_until, '%b %Y'))]

# Define gif folder output, clear the folder if necessary
gif_filepath = os.path.join(HOME_DIR, 'output', 'gif')
if os.path.exists(gif_filepath):
    shutil.rmtree(gif_filepath) 
os.makedirs(gif_filepath)

# Opne Firefox browser
browser = webdriver.Firefox(executable_path=r'{}/geckodriver'.format(HOME_DIR))

# cycle through months and create maps, take screenshot in firefox and save png
for month in time_extent:
    df = get_incidents_by_month(df_eth, month)
    m = generate_map(df, month)
    delay=5
    fn='tempmap.html'
    tmpurl='file://{path}/{mapfile}'.format(path=os.getcwd(),mapfile=fn)
    m.save(fn)
    browser.get(tmpurl)

    #Give the map tiles some time to load
    time.sleep(delay)
    png = os.path.join(gif_filepath, '{}.png'.format(month.strftime('%b_%Y')))
    browser.save_screenshot(png)

    # create a PIL image object
    image = Image.open(png)
    draw = ImageDraw.ImageDraw(image)
    font = ImageFont.truetype(fm.findfont(fm.FontProperties(family='Verdana')), 40)
    
    # draw title
    draw.text((image.width - 400, 20), 
              "{}".format(month.strftime("%b %Y")),
              fill="#ffffff",
             font=font)

    image.save(png, "PNG", optimize=True, quality=95)
    
# Close firefox browser
browser.quit()

# Stitch files together into gif
images = []
files = os.listdir(gif_filepath)
files.sort(key=lambda x: os.path.getmtime(os.path.join(gif_filepath, x)))
for fn in files:
    if fn.endswith('.png'):
        images.append(imageio.imread(os.path.join(gif_filepath, fn)))
imageio.mimsave(os.path.join(HOME_DIR, 'conflict_ethiopia.gif'), images, fps=0.5)


# Display the gif
with open(os.path.join(HOME_DIR, 'conflict_ethiopia.gif'), 'rb') as f:
    display(IPython.display.Image(data=f.read(), format='png', width=800, height=800))