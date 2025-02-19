#! /usr/bin/env python3

"""
ZSpotify
It's like youtube-dl, but for Spotify.
"""

import json
import os
import os.path
import platform
import re
import sys
import time
from getpass import getpass

import music_tag
import requests
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.core import Session
from librespot.metadata import TrackId
from pydub import AudioSegment

SESSION: Session = None
sanitize = ["\\", "/", ":", "*", "?", "'", "<", ">", '"']

ROOT_PATH = "ZSpotify Music/"
SKIP_EXISTING_FILES = True
MUSIC_FORMAT = "mp3"  # or "ogg"
FORCE_PREMIUM = False # set to True if not detecting your premium account automatically
RAW_AUDIO_AS_IS = False # set to True if you wish you save the raw audio without re-encoding it.

# miscellaneous functions for general use


def clear():
    """ Clear the console window """
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


def wait(seconds: int = 3):
    """ Pause for a set number of seconds """
    for i in range(seconds)[::-1]:
        print("\rWait for %d second(s)..." % (i + 1), end="")
        time.sleep(1)


def sanitize_data(value):
    global sanitize
    """ Returns given string with problematic removed """
    for i in sanitize:
        value = value.replace(i, "")
    return value.replace("|", "-")


def splash():
    """ Displays splash screen """
    print("=================================\n"
          "| Spotify Downloader            |\n"
          "|                               |\n"
          "| by Footsiefat/Deathmonger     |\n"
          "=================================\n\n\n")


# two mains functions for logging in and doing client stuff
def login():
    """ Authenticates with Spotify and saves credentials to a file """
    global SESSION

    if os.path.isfile("credentials.json"):
        try:
            SESSION = Session.Builder().stored_file().create()
            return
        except RuntimeError:
            pass
    while True:
        user_name = input("Username: ")
        password = getpass()
        try:
            SESSION = Session.Builder().user_pass(user_name, password).create()
            return
        except RuntimeError:
            pass


def client():
    """ Connects to spotify to perform query's and get songs to download """
    global QUALITY, SESSION
    splash()

    token = SESSION.tokens().get("user-read-email")

    if check_premium(token):
        print("###   DETECTED PREMIUM ACCOUNT - USING VERY_HIGH QUALITY   ###")
        QUALITY = AudioQuality.VERY_HIGH
    else:
        print("###   DETECTED FREE ACCOUNT - USING HIGH QUALITY   ###")
        QUALITY = AudioQuality.HIGH

    if len(sys.argv) > 1:
        if sys.argv[1] == "-p" or sys.argv[1] == "--playlist":
            download_from_user_playlist()
        elif sys.argv[1] == "-ls" or sys.argv[1] == "--liked-songs":
            for song in get_saved_tracks(token):
                download_track(song['track']['id'], "Liked Songs/")
                print("\n")
        else:
            track_uri_search = re.search(
                r"^spotify:track:(?P<TrackID>[0-9a-zA-Z]{22})$", sys.argv[1])
            track_url_search = re.search(
                r"^(https?://)?open\.spotify\.com/track/(?P<TrackID>[0-9a-zA-Z]{22})(\?si=.+?)?$",
                sys.argv[1],
            )

            album_uri_search = re.search(
                r"^spotify:album:(?P<AlbumID>[0-9a-zA-Z]{22})$", sys.argv[1])
            album_url_search = re.search(
                r"^(https?://)?open\.spotify\.com/album/(?P<AlbumID>[0-9a-zA-Z]{22})(\?si=.+?)?$",
                sys.argv[1],
            )

            playlist_uri_search = re.search(
                r"^spotify:playlist:(?P<PlaylistID>[0-9a-zA-Z]{22})$", sys.argv[1])
            playlist_url_search = re.search(
                r"^(https?://)?open\.spotify\.com/playlist/(?P<PlaylistID>[0-9a-zA-Z]{22})(\?si=.+?)?$",
                sys.argv[1],
            )

            if track_uri_search is not None or track_url_search is not None:
                track_id_str = (track_uri_search
                                if track_uri_search is not None else
                                track_url_search).group("TrackID")

                download_track(track_id_str)
            elif album_uri_search is not None or album_url_search is not None:
                album_id_str = (album_uri_search
                                if album_uri_search is not None else
                                album_url_search).group("AlbumID")

                download_album(album_id_str)
            elif playlist_uri_search is not None or playlist_url_search is not None:
                playlist_id_str = (playlist_uri_search
                                   if playlist_uri_search is not None else
                                   playlist_url_search).group("PlaylistID")

                playlist_songs = get_playlist_songs(token, playlist_id_str)
                name, creator = get_playlist_info(token, playlist_id_str)
                for song in playlist_songs:
                    download_track(song['track']['id'],
                                   sanitize_data(name) + "/")
                    print("\n")
    else:
        search_text = input("Enter search: ")
        search(search_text)
    wait()


# related functions that do stuff with the spotify API
def search(search_term):
    """ Searches Spotify's API for relevant data """
    token = SESSION.tokens().get("user-read-email")

    resp = requests.get(
        "https://api.spotify.com/v1/search",
        {
            "limit": "10",
            "offset": "0",
            "q": search_term,
            "type": "track,album,playlist"
        },
        headers={"Authorization": "Bearer %s" % token},
    )

    i = 1
    tracks = resp.json()["tracks"]["items"]
    if len(tracks) > 0:
        print("###  TRACKS  ###")
        for track in tracks:
            print("%d, %s | %s" % (
                i,
                track["name"],
                ",".join([artist["name"] for artist in track["artists"]]),
            ))
            i += 1
        total_tracks = i - 1
        print("\n")
    else:
        total_tracks = 0

    albums = resp.json()["albums"]["items"]
    if len(albums) > 0:
        print("###  ALBUMS  ###")
        for album in albums:
            print("%d, %s | %s" % (
                i,
                album["name"],
                ",".join([artist["name"] for artist in album["artists"]]),
            ))
            i += 1
        total_albums = i - total_tracks - 1
        print("\n")
    else:
        total_albums = 0

    playlists = resp.json()["playlists"]["items"]
    print("###  PLAYLISTS  ###")
    for playlist in playlists:
        print("%d, %s | %s" % (
            i,
            playlist["name"],
            playlist['owner']['display_name'],
        ))
        i += 1
    print("\n")

    if len(tracks) + len(albums) + len(playlists) == 0:
        print("NO RESULTS FOUND - EXITING...")
    else:
        position = int(input("SELECT ITEM BY ID: "))

        if position <= total_tracks:
            track_id = tracks[position - 1]["id"]
            download_track(track_id)
        elif position <= total_albums + total_tracks:
            download_album(albums[position - total_tracks - 1]["id"])
        else:
            playlist_choice = playlists[position -
                                        total_tracks - total_albums - 1]
            playlist_songs = get_playlist_songs(token, playlist_choice['id'])
            for song in playlist_songs:
                if song['track']['id'] is not None:
                    download_track(song['track']['id'], sanitize_data(
                        playlist_choice['name'].strip()) + "/")
                    print("\n")


def get_song_info(song_id):
    """ Retrieves metadata for downloaded songs """
    token = SESSION.tokens().get("user-read-email")

    info = json.loads(requests.get("https://api.spotify.com/v1/tracks?ids=" + song_id +
                      '&market=from_token', headers={"Authorization": "Bearer %s" % token}).text)

    artists = []
    for data in info['tracks'][0]['artists']:
        artists.append(sanitize_data(data['name']))
    album_name = sanitize_data(info['tracks'][0]['album']["name"])
    name = sanitize_data(info['tracks'][0]['name'])
    image_url = info['tracks'][0]['album']['images'][0]['url']
    release_year = info['tracks'][0]['album']['release_date'].split("-")[0]
    disc_number = info['tracks'][0]['disc_number']
    track_number = info['tracks'][0]['track_number']
    scraped_song_id = info['tracks'][0]['id']
    is_playable = info['tracks'][0]['is_playable']

    return artists, album_name, name, image_url, release_year, disc_number, track_number, scraped_song_id, is_playable


def check_premium(access_token):
    global FORCE_PREMIUM
    """ If user has spotify premium return true """
    headers = {'Authorization': f'Bearer {access_token}'}
    resp = requests.get('https://api.spotify.com/v1/me',
                        headers=headers).json()
    return bool(("product" in resp and resp["product"] == "premium") or FORCE_PREMIUM)


# Functions directly related to modifying the downloaded audio and its metadata
def convert_audio_format(filename):
    """ Converts raw audio into playable mp3 or ogg vorbis """
    global MUSIC_FORMAT
    print("###   CONVERTING TO " + MUSIC_FORMAT.upper() + "   ###")
    raw_audio = AudioSegment.from_file(filename, format="ogg",
                                       frame_rate=44100, channels=2, sample_width=2)
    if QUALITY == AudioQuality.VERY_HIGH:
        bitrate = "320k"
    else:
        bitrate = "160k"
    raw_audio.export(filename, format=MUSIC_FORMAT, bitrate=bitrate)


def set_audio_tags(filename, artists, name, album_name, release_year, disc_number, track_number):
    """ sets music_tag metadata """
    print("###   SETTING MUSIC TAGS   ###")
    tags = music_tag.load_file(filename)
    tags['artist'] = conv_artist_format(artists)
    tags['tracktitle'] = name
    tags['album'] = album_name
    tags['year'] = release_year
    tags['discnumber'] = disc_number
    tags['tracknumber'] = track_number
    tags.save()


def set_music_thumbnail(filename, image_url):
    """ Downloads cover artwork """
    print("###   SETTING THUMBNAIL   ###")
    img = requests.get(image_url).content
    tags = music_tag.load_file(filename)
    tags['artwork'] = img
    tags.save()


def conv_artist_format(artists):
    """ Returns converted artist format """
    formatted = ""
    for x in artists:
        formatted += x + ", "
    return formatted[:-2]


# Extra functions directly related to spotify playlists
def get_all_playlists(access_token):
    """ Returns list of users playlists """
    playlists = []
    limit = 50
    offset = 0

    while True:
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'limit': limit, 'offset': offset}
        resp = requests.get("https://api.spotify.com/v1/me/playlists",
                            headers=headers, params=params).json()
        offset += limit
        playlists.extend(resp['items'])

        if len(resp['items']) < limit:
            break

    return playlists


def get_playlist_songs(access_token, playlist_id):
    """ returns list of songs in a playlist """
    songs = []
    offset = 0
    limit = 100

    while True:
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'limit': limit, 'offset': offset}
        resp = requests.get(
            f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks', headers=headers, params=params).json()
        offset += limit
        songs.extend(resp['items'])

        if len(resp['items']) < limit:
            break

    return songs


def get_playlist_info(access_token, playlist_id):
    """ Returns information scraped from playlist """
    headers = {'Authorization': f'Bearer {access_token}'}
    resp = requests.get(
        f'https://api.spotify.com/v1/playlists/{playlist_id}?fields=name,owner(display_name)&market=from_token', headers=headers).json()
    return resp['name'].strip(), resp['owner']['display_name'].strip()


# Extra functions directly related to spotify albums
def get_album_tracks(access_token, album_id):
    """ Returns album tracklist """
    songs = []
    offset = 0
    limit = 50

    while True:
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'limit': limit, 'offset': offset}
        resp = requests.get(
            f'https://api.spotify.com/v1/albums/{album_id}/tracks', headers=headers, params=params).json()
        offset += limit
        songs.extend(resp['items'])

        if len(resp['items']) < limit:
            break

    return songs


def get_album_name(access_token, album_id):
    """ Returns album name """
    headers = {'Authorization': f'Bearer {access_token}'}
    resp = requests.get(
        f'https://api.spotify.com/v1/albums/{album_id}', headers=headers).json()
    return resp['artists'][0]['name'], sanitize_data(resp['name'])


# Extra functions directly related to our saved tracks
def get_saved_tracks(access_token):
    """ Returns user's saved tracks """
    songs = []
    offset = 0
    limit = 50

    while True:
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'limit': limit, 'offset': offset}
        resp = requests.get('https://api.spotify.com/v1/me/tracks',
                            headers=headers, params=params).json()
        offset += limit
        songs.extend(resp['items'])

        if len(resp['items']) < limit:
            break

    return songs


# Functions directly related to downloading stuff
def download_track(track_id_str: str, extra_paths=""):
    """ Downloads raw song audio from Spotify """
    global ROOT_PATH, SKIP_EXISTING_FILES, MUSIC_FORMAT, RAW_AUDIO_AS_IS

    track_id = TrackId.from_base62(track_id_str)
    artists, album_name, name, image_url, release_year, disc_number, track_number, scraped_song_id, is_playable = get_song_info(
        track_id_str)

    song_name = artists[0] + " - " + name
    filename = ROOT_PATH + extra_paths + song_name + '.' + MUSIC_FORMAT

    if not is_playable:
        print("###   SKIPPING:", song_name, "(SONG IS UNAVAILABLE)   ###")
    else:
        if os.path.isfile(filename) and SKIP_EXISTING_FILES:
            print("###   SKIPPING:", song_name, "(SONG ALREADY EXISTS)   ###")
        else:
            if track_id_str != scraped_song_id:
                print("###   APPLYING PATCH TO LET SONG DOWNLOAD   ###")
                track_id_str = scraped_song_id
                track_id = TrackId.from_base62(track_id_str)

            print("###   FOUND SONG:", song_name, "   ###")

            try:
                stream = SESSION.content_feeder().load(
                    track_id, VorbisOnlyAudioQuality(QUALITY), False, None)
            except:
                print("###   SKIPPING:", song_name,
                      "(GENERAL DOWNLOAD ERROR)   ###")
            else:
                print("###   DOWNLOADING RAW AUDIO   ###")

                if not os.path.isdir(ROOT_PATH + extra_paths):
                    os.makedirs(ROOT_PATH + extra_paths)

                with open(filename, 'wb') as file:
                    # Try's to download the entire track at once now to be more efficient.
                    byte = stream.input_stream.stream().read(-1)
                    file.write(byte)
                if not RAW_AUDIO_AS_IS:
                    try:
                        convert_audio_format(filename)
                    except:
                        os.remove(filename)
                        print("###   SKIPPING:", song_name,
                            "(GENERAL CONVERSION ERROR)   ###")
                    else:
                        set_audio_tags(filename, artists, name, album_name,
                                    release_year, disc_number, track_number)
                        set_music_thumbnail(filename, image_url)


def download_album(album):
    """ Downloads songs from an album """
    token = SESSION.tokens().get("user-read-email")
    artist, album_name = get_album_name(token, album)
    tracks = get_album_tracks(token, album)
    for track in tracks:
        download_track(track['id'], artist + " - " + album_name + "/")
        print("\n")


def download_from_user_playlist():
    """ Downloads songs from users playlist """
    token = SESSION.tokens().get("user-read-email")
    playlists = get_all_playlists(token)

    count = 1
    for playlist in playlists:
        print(str(count) + ": " + playlist['name'].strip())
        count += 1

    playlist_choice = input("SELECT A PLAYLIST BY ID: ")
    playlist_songs = get_playlist_songs(
        token, playlists[int(playlist_choice) - 1]['id'])
    for song in playlist_songs:
        if song['track']['id'] is not None:
            download_track(song['track']['id'], sanitize_data(
                playlists[int(playlist_choice) - 1]['name'].strip()) + "/")
        print("\n")

# Core functions here

def checkRaw():
    global RAW_AUDIO_AS_IS, MUSIC_FORMAT
    if RAW_AUDIO_AS_IS:
        MUSIC_FORMAT = "raw"

def main():
    """ Main function """
    checkRaw()
    login()
    client()


if __name__ == "__main__":
    main()
