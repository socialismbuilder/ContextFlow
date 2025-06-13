import re
from .config_manager import get_config

def Process_front_html(showing_sentence):

    pattern = re.compile(r'<u>(.*?)</u>')
    showing_sentence = pattern.sub(r'<span class="highlight">\1</span> ', showing_sentence)
    
    return f"""
    <style>
        .card-group {{
            border: 1px solid rgba(0, 0, 0, 0.1); /* 调整白天模式边框 */
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            background: rgba(0, 0, 0, 0.03); /* 调整白天模式背景 */
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1); /* 添加投影 */
        }}
        .night_mode .card-group {{
            border: 1px solid rgba(0, 0, 0, 0.2); /* 夜间模式边框 */
            background: rgba(0, 0, 0, 0.1); /* 夜间模式背景 */
        }}
        .label {{
            font-size: 14px;
            color: #aaa;
            margin-bottom: 5px;
            text-transform: uppercase;
        }}
        .night_mode .label {{
            color: #777;
        }}
        .card-text {{
            font-size: 36px;
            font-weight: bold;
            line-height: 1.3;
            margin-bottom: 10px;
            color: black; /* 正常模式默认颜色 */
        }}
        .night_mode .card-text {{
            color: white; /* 夜间模式颜色 */
        }}
        .highlight {{
            border-radius:8px; 
            background-color:rgba(255, 150, 150, 0.7); 
            padding:4px 8px;
        }}
        .translation-placeholder-line {{
            height:18px; 
            width:80%; /* 保持宽度，但取消居中 */
            background:#e0e0e0;
            border-radius:9px; 
            margin:0 0 8px 0; /* 靠左显示 */
        }}
        .translation-placeholder-line:last-child {{
            width:55%; /* 保持宽度，但取消居中 */
            margin:0 0 0 0; /* 靠左显示 */
        }}
        .night_mode .translation-placeholder-line {{
            background: rgba(128, 128, 128, 0.7);
        }}
    </style>
    <div style="margin: 10px;">
        <!-- 例句和翻译组 -->
        <div class="card-group">
            <div class="label">例句</div>
            <div class="card-text">{showing_sentence}</div>

            <div class="label" style="margin-top: 15px;">翻译</div>
            <div class="card-text" style="line-height: 1.4; opacity: 0.9;">
                <div class="translation-placeholder-line"></div>
                <div class="translation-placeholder-line"></div>
            </div>
        </div>
    </div>
    """

def Process_back_html(showing_sentence, showing_translation, html):

    pattern = re.compile(r'<u>(.*?)</u>')
    showing_sentence = pattern.sub(r'<span class="highlight">\1</span> ', showing_sentence)
    showing_translation = pattern.sub(r'<span class="highlight">\1</span> ', showing_translation)
    
    return f"""
    <style>
        .card-group {{
            border: 1px solid rgba(0, 0, 0, 0.1); /* 调整白天模式边框 */
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            background: rgba(0, 0, 0, 0.03); /* 调整白天模式背景 */
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1); /* 添加投影 */
        }}
        .night_mode .card-group {{
            border: 1px solid rgba(0, 0, 0, 0.2); /* 夜间模式边框 */
            background: rgba(0, 0, 0, 0.1); /* 夜间模式背景 */
        }}
        .label {{
            font-size: 14px;
            color: #aaa;
            margin-bottom: 5px;
            text-transform: uppercase;
        }}
        .night_mode .label {{
            color: #777;
        }}
        .card-text {{
            font-size: 36px;
            font-weight: bold;
            line-height: 1.3;
            margin-bottom: 10px;
            color: black; /* 正常模式默认颜色 */
        }}
        .night_mode .card-text {{
            color: white; /* 夜间模式颜色 */
        }}
        .highlight {{
            border-radius:8px; 
            background-color:rgba(255, 150, 150, 0.7); 
            padding:4px 8px;
        }}
        .original-card-text {{
            font-size: 24px;
            line-height: 1.4;
            opacity: 0.8;
            color: black; /* 正常模式默认颜色 */
        }}
        .night_mode .original-card-text {{
            color: white; /* 夜间模式颜色 */
        }}
    </style>
    <div style="margin: 10px;">
        <!-- 例句和翻译组 -->
        <div class="card-group">
            <div class="label">例句</div>
            <div class="card-text">{showing_sentence}</div>

            <div class="label" style="margin-top: 15px;">翻译</div>
            <div class="card-text" style="line-height: 1.4; opacity: 0.9;">{showing_translation}</div>
        </div>

        <!-- 原始卡片组 -->
        <div class="card-group">
            <div class="label" style="color: #777;">原始卡片</div>
            <div class="original-card-text">{html}</div>
        </div>
    </div>
    """
