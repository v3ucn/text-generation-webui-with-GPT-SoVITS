import time
from pathlib import Path

import gradio as gr

from modules import chat, shared
from modules.html_generator import chat_html_wrapper

import json

import requests

params = {
    'activate': True,
    'speaker': '默认模型',
    'language': '默认语言',
    'speech_key': None,
    'speech_region': None,
    'show_text': True,
    'autoplay': True,
    'apiurl': "http://localhost:9880/tts_to_audio/",
    'voice_pitch': 'default',
    'voice_speed': 'default',
    'local_cache_path': ''  # User can override the default cache path to something other via settings.json
}

current_params = params.copy()
# Find voices here: https://speech.microsoft.com/portal/voicegallery
voices = ['en-US-JennyNeural', 'en-US-AriaNeural', 'en-US-SaraNeural', 'en-US-DavisNeural', 'en-US-GuyNeural', 'en-US-TonyNeural']
# Learn about defining ssml properties (pitch, speed, etc.) here: https://learn.microsoft.com/en-us/azure/cognitive-services/speech-service/speech-synthesis-markup-voice#adjust-prosody
voice_pitches = ['default', 'x-low', 'low', 'medium', 'high', 'x-high']
voice_speeds = ['default', 'x-slow', 'slow', 'medium', 'fast', 'x-fast']

# Used for making text xml compatible, needed for voice pitch and speed control
table = str.maketrans({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    "'": "&apos;",
    '"': "&quot;",
})


def xmlesc(txt):
    return txt.translate(table)


def load_synth():
    speech_config = speechsdk.SpeechConfig(subscription=params['speech_key'], region=params['speech_region'])
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    return speech_synthesizer



def remove_tts_from_history(history):
    for i, entry in enumerate(history['internal']):
        history['visible'][i] = [history['visible'][i][0], entry[1]]

    return history


def toggle_text_in_history(name1, name2, mode, style):
    for i, entry in enumerate(shared.history['visible']):
        visible_reply = entry[1]
        if visible_reply.startswith('<audio'):
            if params['show_text']:
                reply = shared.history['internal'][i][1]
                shared.history['visible'][i] = [shared.history['visible'][i][0], f"{visible_reply.split('</audio>')[0]}</audio>\n\n{reply}"]
            else:
                shared.history['visible'][i] = [shared.history['visible'][i][0], f"{visible_reply.split('</audio>')[0]}</audio>"]

    return chat_html_wrapper(shared.history['visible'], name1, name2, mode, style)


def state_modifier(state):
    state['stream'] = False
    return state

def input_modifier(string, state):
    if not params['activate']:
        return string

    shared.processing_message = "*Is recording a voice message...*"
    return string


def history_modifier(history):
    # Remove autoplay from the last reply
    if len(history['internal']) > 0:
        history['visible'][-1] = [
            history['visible'][-1][0],
            history['visible'][-1][1].replace('controls autoplay>', 'controls>')
        ]

    return history


def output_modifier(string):
    """
    This function is applied to the model outputs.
    """

    global model, current_params, streaming_state

    for i in params:
        if params[i] != current_params[i]:
            model = load_synth()
            current_params = params.copy()
            break

    if not params['activate']:
        return string

    original_string = string


    if string == '':
        string = '*Empty reply, try regenerating*'
    else:
        output_file = Path(f'extensions/text-gen-webui-gpt-sovits/outputs/{int(time.time())}.wav')
        ssml_tags=f'<voice name="{params["speaker"]}"><prosody pitch="{params["voice_pitch"]}" rate="{params["voice_speed"]}">'
        ssml_string  = f'<speak version="1.0" xmlns="https://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{params["language"]}">{ssml_tags}{xmlesc(string)}</prosody></voice></speak>'


        data = json.dumps({"text":string})#转换为json字符串
        headers = {"Content-Type":"application/json"}#指定提交的是json
        r = requests.post(f'{params["apiurl"]}',data=data,headers=headers)

        with open(output_file, 'wb') as audio_file:
            audio_file.write(r.content)

        
        autoplay = 'autoplay' if params['autoplay'] else ''
        string = f'<audio src="file/{output_file.as_posix()}" controls {autoplay}></audio>'
        if params['show_text']:
            string += f'\n\n{original_string}'

    shared.processing_message = "*Is typing...*"
    return string


def setup():
    pass


def ui():
    # Gradio elements
    with gr.Accordion("TTS"):
        with gr.Row():
            activate = gr.Checkbox(value=params['activate'], label='激活TTS')
            autoplay = gr.Checkbox(value=params['autoplay'], label='自动播放')

        show_text = gr.Checkbox(value=params['show_text'], label='Show message text under audio player')
        with gr.Row():
            api_url = gr.Textbox(label="GPT-SoVITS接口地址,也可以是别的接口地址,比如Bert-vits2", value=params['apiurl'])


    # Toggle message text in history
    show_text.change(lambda x: params.update({"show_text": x}), show_text, None)
    show_text.change(toggle_text_in_history, [shared.gradio[k] for k in ['name1', 'name2', 'mode', 'chat_style']], shared.gradio['display'])
    show_text.change(chat.save_history, shared.gradio['mode'], [], show_progress=False)

    # Event functions to update the parameters in the backend
    activate.change(lambda x: params.update({"activate": x}), activate, None)
    autoplay.change(lambda x: params.update({"autoplay": x}), autoplay, None)
    api_url.change(lambda x: params.update({"apiurl": x}), api_url, None)