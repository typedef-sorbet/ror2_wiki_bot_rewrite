import discord
import config
import urllib
import requests
import logging

from discord.ext import commands
from bs4 import BeautifulSoup as Soup

logging.basicConfig(level=logging.INFO)
bot = commands.Bot(command_prefix="!")

# Trick the wiki into thinking we're a browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 \
    (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
}

# Util functions here
def urlFormat(s):
    return urllib.parse.quote(s.encode("utf-8"))

def urlFromQueryText(query):
    # Search the Risk of Rain 2 wiki for the stubbed text, and return the text of the first search result.
    global headers
    full_url = f"https://riskofrain2.fandom.com/wiki/Special:Search?query={urlFormat(query)}&scope=internal&navigationSearch=true"
    response = requests.get(full_url, headers=headers)

    if 199 < response.status_code < 300:
        soup = Soup(response.text, "html.parser")

        # This returns a ResultSet object, which is a list of Tag objects, which contain tag attrs as a dictionary
        element = soup.select(".unified-search__result__link")

        print(f"Resolved query {query} to url {element[0]['href']}")

        return element[0]["href"]
    else:
        print(f"Got error while searching wiki")

def renderMessage(data):
    # Render the data struct as a text message depending on the contents of the data.
    match data:
        case {"Categories": ["Newt Altars"], "WikiUrl": url, "StageName": stageName, "Locations": locations, "Images": images}:
            print("Rendering data as Newt Altar data...")
            return f"** Newt Altars on {stageName} **\n"

        case {"Categories": list() as cats, "WikiUrl": url, "SurvivorStats": survivorStats, "SurvivorName": survivorName} if "Survivors" in cats:
            print("Rendering data as Survivor data...")
            return '\n'.join((
                f"**{survivorName}**",
                "",
                f"_Health_:     {survivorStats['Health']}",
                f"_Regen_:      {survivorStats['Health Regen']}",
                f"_Damage_:     {survivorStats['Damage']}",
                f"_Speed_:      {survivorStats['Speed']}",
                f"_Armor_:      {survivorStats['Armor']}",
                "",
                f"{url}"
            ))

        case {"Categories": list() as cats, "WikiUrl": url, "ItemStats": itemStats, "ItemName": itemName, "ItemDescription": itemDescription} if "Items" in cats:
            print("Rendering data as Item data...")
            return '\n'.join((
                f"**{itemName}**",
                "",
                f"{itemDescription}",
                "",
                *[f"**{entry['Stat']}**: {entry['Value']} _({entry['StackAmount']} stacked {entry['StackType']})_" for entry in itemStats],   # This may by the single worst line of python I've ever written, sorry deckle
                "",
                f"{url}"
            ))

        case _:
            print(f"Unknown data type: categories {data['Categories']}")
            print(data)

async def sendMessageFromData(ctx, data):
    # Render the data contained in the data struct, and send it
    try:
        await ctx.send(renderMessage(data))

        if "Images" in data:
            for idx, img in enumerate(data["Images"]):
                if "Locations" in data and idx >= len(data["Locations"]):
                    break
                else:
                    embed = discord.Embed(description=data["Locations"][idx])
                    embed.set_image(url=img)
                    await ctx.send(embed=embed)
    except discord.HTTPException as httpErr:
        print(f"Failed to send message: {httpErr}")
        return None
    except discord.Forbidden as forbiddenErr:
        print(f"Improper permissions to send message: {forbiddenErr}")
        return None
    except discord.InvalidArgument as invalidErr:
        print(f"Invalid message argument: {invalidErr}")
        return None

# Bot commands go here...
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("-----")

@bot.command(name="ping")
async def _ping(ctx):
    print("Got ping")
    await ctx.send("Pong!")

@bot.command(name="newt")
async def _get_newt_altars(ctx, *, query):
    print(f"Got command \"newt\" with query string {query}")
    envUrl = urlFromQueryText(query)

    httpResp = requests.get(envUrl, headers=headers)

    if 199 < httpResp.status_code < 300:
        soup = Soup(httpResp.text, "html.parser")

        # Double-check that this page is actually an environment.
        categoryNodes = soup.select("div.page-header__categories a")

        for tag in categoryNodes:
            if tag.string == "Environments":
                break
        else:
            print(f"Page {envUrl} does not describe an environment; categories: {str([t.string for t in categoryNodes])}")
            return
        
        data = {
            "WikiUrl": envUrl,
            "Categories": ["Newt Altars"]
        }

        # Get the page name.
        data["StageName"] = ''.join(soup.select("h1#firstHeading")[0].string.split())

        # Look for the Newt Altar section on the wiki.
        newtAltarSpan = soup.select("h2 span#Newt_Altars")

        # Check to make sure we actually grabbed something there.
        if newtAltarSpan:
            # newtAltarSpan grabbed the span inside of an <h2> tag. The list we want is a *sibling* of that tag. Find it.
            nodePtr = newtAltarSpan[0].parent

            while nodePtr.name != "ol":
                nodePtr = nodePtr.next_sibling

            # We should now have arrived at the ordered list tag.

            data["Locations"] = []

            for li in nodePtr.children:
                if li.string != "\n":
                    data["Locations"].append(li.string)

            # Now, grab the href of the images for each of those locations.
            data["Images"] = []

            imageNodes = soup.select("img")

            for img in imageNodes:
                if "data-image-key" in img.attrs and "_NA" in img["data-image-key"]:
                    data["Images"].append(img.parent["href"])

            # Pass the data off to the info renderer, and send the message.
            await sendMessageFromData(ctx, data)

        else:
            print(f"Stage does not have any Newt Altars?")

    else:
        print(f"Got error while pulling up environment page for {envUrl}")

@bot.command(name="wiki")
async def _get_wiki_page(ctx, *, query):
    print(f"Got command \"wiki\" with query string {query}")
    wikiUrl = urlFromQueryText(query)

    httpResp = requests.get(wikiUrl, headers=headers)

    if 199 < httpResp.status_code < 300:
        soup = Soup(httpResp.text, "html.parser")

        categoryNodes = soup.select("div.page-header__categories a")
        
        data = {
            "WikiUrl": wikiUrl,
            "Categories": [cat.string for cat in categoryNodes]
        }

        if "Survivors" in data["Categories"]:
            infoItems = soup.select("table.infoboxtable tbody tr")

            data["SurvivorStats"] = {}

            for item in infoItems:
                # For some reason, this child list can contain tags that are just newlines.
                # Remove them.
                contents = list(filter(lambda ent: ent != "\n", item.contents))
                if len(contents) == 1 and contents[0].name == "th":
                    data["SurvivorName"] = contents[0].string.replace("\n", "")
                elif len(contents) == 2:
                    data["SurvivorStats"][''.join(contents[0].strings).replace("\n", "")] = ''.join(contents[1].strings).replace("\n", "")
        elif "Items" in data["Categories"]:
            infoItems = soup.select("table.infoboxtable tbody tr")

            statMode = False

            data["ItemStats"] = []

            for idx, item in enumerate(infoItems):
                # For some reason, this child list can contain tags that are just newlines.
                # Remove them.
                contents = list(filter(lambda ent: ent != "\n", item.contents))

                if len(contents) == 1:
                    if contents[0].name == "th" and idx == 0:
                        data["ItemName"] = contents[0].string.replace("\n", "")
                    elif contents[0].name == "td":
                        data["ItemDescription"] = ''.join(contents[0].strings).replace("\n", "")
                elif contents[0].string and "Stat" in contents[0].string:
                    statMode = True
                elif statMode:
                    data["ItemStats"].append({attr: ''.join(tag.strings).replace("\n", "") for attr, tag in zip(["Stat", "Value", "StackType", "StackAmount"], contents)})  # this is also pretty bad
        else:
            print(f"Unsupported page; categories {data['Categories']}")
            return

        await sendMessageFromData(ctx, data)
    else:
        print(f"Got error while pulling up environment page for {envUrl}")

@bot.command(name="github")
async def _git(ctx):
    # TODO
    await ctx.send("You can find the source code for this bot on [GitHub!](https://github.com/warnespe001/ror2_wiki_bot_rewrite)")

if __name__ == "__main__":
    bot.run(config.token())
