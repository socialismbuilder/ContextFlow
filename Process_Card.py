import re
from .config_manager import get_config

def Process_front_html(showing_sentence):

    pattern = re.compile(r'<u>(.*?)</u>')
    showing_sentence = pattern.sub(r'<span style="border-radius:8px; background-color:rgba(255, 150, 150, 0.7); padding:4px 8px;">\1</span> ', showing_sentence)
    
    return f"""
    <div style="margin: 10px;">
        <!-- 例句卡片 -->
        <div style="
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            background: rgba(255, 255, 255, 0.05);
        ">
            <div style="
                font-size: 14px;
                color: #aaa;
                margin-bottom: 5px;
                text-transform: uppercase;
            ">例句</div>
            <div style="
                font-size: 36px;
                font-weight: bold;
                line-height: 1.3;
                margin-bottom: 10px;
            ">{showing_sentence}</div>
        </div>""" 

def Process_back_html(showing_sentence, showing_translation, html):

    pattern = re.compile(r'<u>(.*?)</u>')
    showing_sentence = pattern.sub(r'<span style="border-radius:8px; background-color:rgba(255, 150, 150, 0.7); padding:4px 8px;">\1</span> ', showing_sentence)
    showing_translation = pattern.sub(r'<span style="border-radius:8px; background-color:rgba(255, 150, 150, 0.7); padding:4px 8px;">\1</span> ', showing_translation)
    
    return f"""
    <div style="margin: 10px;">
        <!-- 例句卡片 -->
        <div style="
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            background: rgba(255, 255, 255, 0.05);
        ">
            <div style="
                font-size: 14px;
                color: #aaa;
                margin-bottom: 5px;
                text-transform: uppercase;
            ">例句</div>
            <div style="
                font-size: 36px;
                font-weight: bold;
                line-height: 1.3;
                margin-bottom: 10px;
            ">{showing_sentence}</div>
        </div>

        <!-- 翻译卡片 -->
        <div style="
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            background: rgba(255, 255, 255, 0.05);
        ">
            <div style="
                font-size: 14px;
                color: #aaa;
                margin-bottom: 5px;
                text-transform: uppercase;
            ">翻译</div>
            <div style="
                font-size: 36px;
                line-height: 1.4;
                opacity: 0.9;
            ">{showing_translation}</div>
        </div>

        <!-- 原始卡片（带标题） -->
        <div style="
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 15px;
            background: rgba(255, 255, 255, 0.03);
        ">
            <div style="
                font-size: 14px;
                color: #777;
                margin-bottom: 10px;
                text-transform: uppercase;
            ">原始卡片</div>
            <div style="
                font-size: 14px;
                line-height: 1.4;
                opacity: 0.8;
            ">{html}</div>
        </div>
    </div>
    """

