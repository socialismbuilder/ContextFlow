/**
 * 「卡片平均用时」注入脚本模板（由 ui/avg_time_injection.py 读取并替换占位符后执行）
 *
 * 占位符：
 *   __DATA__     —— {deck, todayYear, series:[{d,s,n,t}], ranges:[{cards,seconds,median}]}
 *   __OPTIONS__  —— [{label, days, barDays}]（barDays=0 表示按柱数上限自动分桶）
 *   __DEFAULT__  —— 默认选中的范围下标
 *   __MAXBARS__  —— 任意范围允许的最大柱子数
 *
 * 样式全部复用 Anki 原生统计页的全局编译类（Svelte scoped CSS）：
 *   svelte-zuiu8u 卡片外壳 / svelte-161b58q radio 组 / svelte-2itjvo 坐标刻度 /
 *   svelte-rl3mgq 悬浮高亮列 / svelte-19er4xn 底部统计表
 */
(function () {
  var DATA = __DATA__;
  var CARD_ID = "cf-avg-time-card";
  var OPTIONS = __OPTIONS__;
  var current = __DEFAULT__;

  // ---- 图表几何参数（与原生图表一致）----
  var X0 = 70, X1 = 530, Y_TOP = 20, Y_BOT = 225;

  function fmtCards(n) { return n.toLocaleString("en-US"); }

  function fmtDuration(sec) {
    if (sec == null || !isFinite(sec)) return "—";
    if (sec < 60) return sec.toFixed(1) + " 秒";
    if (sec < 3600) return (sec / 60).toFixed(1) + " 分";
    return (sec / 3600).toFixed(2) + " 小时";
  }

  function niceMax(v) {
    if (!v || v <= 0) return 1;
    // 取「4 等分坐标轴后每条刻度都整洁」的最小上限，
    // 阶梯为 4×[1, 1.5, 2, 2.5, 3, 4, 5, 6, 8]×10^e（如 21 → 24，而不是跳到 50）
    var bases = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8];
    var e = Math.floor(Math.log10(v / 4));
    for (var d = e - 1; d <= e + 2; d++) {
      var pow = Math.pow(10, d);
      for (var i = 0; i < bases.length; i++) {
        var max = bases[i] * 4 * pow;
        if (max >= v) return max;
      }
    }
    return v;
  }

  function fmtNum(x) {
    var r = Math.round(x * 10) / 10;
    return r % 1 === 0 ? String(r) : r.toFixed(1);
  }

  function fmtTick(sec, maxSec) {
    // 4 分钟以内一律用秒做刻度（避免出现 0.4 分这种别扭读数）
    if (maxSec < 240) return fmtNum(sec) + " 秒";
    return fmtNum(sec / 60) + " 分";
  }

  // 柱子刻度标签：跨年数据显示完整日期，否则只显示月-日
  function fmtDayLabel(iso) {
    return iso.slice(0, 4) === String(DATA.todayYear) ? iso.slice(5) : iso;
  }

  // 值越大颜色越深，模拟原生柱状图的配色（浅蓝 -> 深蓝）
  function barColor(frac) {
    var a = [212, 228, 244], b = [24, 100, 170];
    var c = a.map(function (av, i) {
      return Math.round(av + (b[i] - av) * Math.max(0, Math.min(1, frac)));
    });
    return "rgb(" + c.join(", ") + ")";
  }

  // 把按天数据按 barDays 聚合成柱：[{d0,d1,cards,secs}]
  function bucketize(win, barDays) {
    var buckets = [];
    for (var i = 0; i < win.length; i += barDays) {
      var cards = 0, secs = 0;
      for (var k = i; k < Math.min(i + barDays, win.length); k++) {
        cards += win[k].n;
        secs += win[k].t;
      }
      buckets.push({ d0: win[i].d, d1: win[Math.min(i + barDays, win.length) - 1].d,
                     cards: cards, secs: secs });
    }
    return buckets;
  }

  function renderChart(card) {
    var opt = OPTIONS[current];
    var win = opt.days > 0 ? DATA.series.slice(Math.max(0, DATA.series.length - opt.days)) : DATA.series;
    var barDays = opt.barDays > 0 ? opt.barDays : Math.max(1, Math.ceil(win.length / __MAXBARS__));
    var buckets = bucketize(win, barDays);
    var len = buckets.length;
    var barW = (X1 - X0) / Math.max(1, len);

    var maxSec = 0;
    buckets.forEach(function (b) {
      if (b.cards > 0) maxSec = Math.max(maxSec, b.secs / b.cards);
    });
    maxSec = niceMax(maxSec * 1.05);
    var yOf = function (s) { return Y_BOT - (s / maxSec) * (Y_BOT - Y_TOP); };

    // ---- 柱状（无复习的天画 0 高度柱，与原生一致）----
    var bars = "";
    var hover = "";
    buckets.forEach(function (b, i) {
      var x = X0 + i * barW;
      var avg = b.cards > 0 ? b.secs / b.cards : null;
      var y = avg == null ? Y_BOT : yOf(avg);
      var h = avg == null ? 0 : Y_BOT - y;
      bars += '<rect rx="1" x="' + x + '" y="' + y + '" height="' + h + '" width="' + barW
        + '" fill="' + barColor(maxSec ? (avg || 0) / maxSec : 0) + '"></rect>';
      hover += '<rect data-i="' + i + '" x="' + x + '" y="' + Y_TOP + '" width="' + barW
        + '" height="' + (Y_BOT - Y_TOP) + '"></rect>';
    });
    var barsG = '<g class="bars">' + bars + '</g>';

    // ---- 坐标轴（复用原生刻度类，刻度对齐柱子中心）----
    var xStep = Math.max(1, Math.round(len / 6));
    var xTicks = "";
    for (var i = 0; i < len; i += xStep) {
      var tx = X0 + (i + 0.5) * barW;
      xTicks += '<g class="tick" opacity="1" transform="translate(' + tx + ',0)">'
        + '<line stroke="currentColor" y2="6"></line>'
        + '<text fill="currentColor" y="9" dy="0.71em" direction="ltr">'
        + fmtDayLabel(buckets[i].d0) + '</text></g>';
    }
    var xG = '<g class="x-ticks svelte-2itjvo" transform="translate(0, ' + Y_BOT + ')" fill="none"'
      + ' font-size="10" font-family="sans-serif" text-anchor="middle">'
      + '<path class="domain" stroke="currentColor" d="M' + X0 + ',0H' + X1 + '"></path>' + xTicks + '</g>';

    var yTicks = "";
    for (var k = 0; k <= 4; k++) {
      var frac = k / 4;
      var vy = Y_BOT - frac * (Y_BOT - Y_TOP);
      yTicks += '<g class="tick" opacity="1" transform="translate(0,' + vy + ')">'
        + '<line stroke="currentColor" x2="-6"></line>'
        + '<text fill="currentColor" x="-9" dy="0.32em">' + fmtTick(maxSec * frac, maxSec) + '</text></g>';
    }
    var yG = '<g class="y-ticks svelte-2itjvo" transform="translate(' + X0 + ', 0)" fill="none"'
      + ' font-size="10" font-family="sans-serif" text-anchor="end" direction="ltr">'
      + '<path class="domain" stroke="currentColor" d="M0,' + Y_BOT + 'V' + Y_TOP + '"></path>' + yTicks + '</g>';

    var noData = maxSec <= 0
      ? '<g class="no-data svelte-adkmdc" pointer-events="none" opacity="1">'
        + '<rect class="svelte-adkmdc" x="0" y="0" width="600" height="250"></rect>'
        + '<text class="svelte-adkmdc" x="300" y="125">无数据</text></g>'
      : "";

    var svg = '<svg viewBox="0 0 600 250">' + barsG + xG + yG + noData
      + '<g class="hover-columns svelte-rl3mgq">' + hover + '</g></svg>';

    // ---- 底部统计行（复用原生「新增」图表的表格样式）----
    var st = DATA.ranges[current];
    var table = '<div class="svelte-19er4xn"><table dir="ltr"><tbody>';
    table += '<tr><td class="align-end svelte-19er4xn">总计:</td>'
      + '<td class="align-start svelte-19er4xn">' + fmtCards(st.cards) + ' 张卡片</td></tr>';
    table += '<tr><td class="align-end svelte-19er4xn">平均:</td>'
      + '<td class="align-start svelte-19er4xn">'
      + (st.cards > 0 ? fmtDuration(st.seconds / st.cards) + " /张" : "—") + '</td></tr>';
    table += '<tr><td class="align-end svelte-19er4xn">中位数:</td>'
      + '<td class="align-start svelte-19er4xn">'
      + (st.median != null ? fmtDuration(st.median) + " /张" : "—") + '</td></tr>';
    table += '</tbody></table></div>';

    var chart = card.querySelector(".cf-chart");
    chart.innerHTML = svg + table;

    // ---- 悬浮提示：显示该柱的 日期 / 卡片数 / 总用时 / 平均 ----
    var tip = document.createElement("div");
    tip.className = "cf-tooltip";
    tip.style.cssText = "position:absolute;display:none;pointer-events:none;z-index:50;"
      + "background:rgba(30,30,30,.92);color:#fff;padding:6px 10px;border-radius:6px;"
      + "font-size:12px;line-height:1.5;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.35);";
    chart.style.position = "relative";
    chart.appendChild(tip);

    chart.querySelectorAll(".hover-columns rect").forEach(function (r) {
      var b = buckets[parseInt(r.getAttribute("data-i"), 10)];
      var label = b.d0 === b.d1 ? b.d0 : b.d0 + " ~ " + b.d1;
      function show(ev) {
        tip.innerHTML = '<b>' + label + '</b><br>'
          + (b.cards > 0
             ? fmtCards(b.cards) + ' 张卡片<br>总用时 '
               + fmtDuration(b.secs) + '<br>平均 ' + fmtDuration(b.secs / b.cards) + ' /张'
             : '无复习记录');
        tip.style.display = "block";
        move(ev);
      }
      function move(ev) {
        var rect = chart.getBoundingClientRect();
        var x = ev.clientX - rect.left + 14;
        var y = ev.clientY - rect.top - 10;
        if (x + tip.offsetWidth > rect.width) x = ev.clientX - rect.left - tip.offsetWidth - 14;
        tip.style.left = x + "px";
        tip.style.top = y + "px";
      }
      r.addEventListener("mouseenter", show);
      r.addEventListener("mousemove", move);
      r.addEventListener("mouseleave", function () { tip.style.display = "none"; });
    });
  }

  function buildCard() {
    var card = document.createElement("div");
    card.id = CARD_ID;
    card.className = "container d-flex flex-column svelte-zuiu8u dark";
    card.style.setProperty("--gutter-block", "2px");
    card.style.setProperty("--container-margin", "0");

    var html = '<div class="position-relative">';
    html += '<h1 class="svelte-zuiu8u">卡片平均用时</h1></div>';
    html += '<div class="graph d-flex flex-grow-1 flex-column justify-content-center svelte-1pm718f">';
    html += '<div class="subtitle svelte-1pm718f"></div>';
    html += '<div class="svelte-161b58q" dir="ltr">';
    OPTIONS.forEach(function (opt, idx) {
      html += '<label><input type="radio" name="cf-avg-time-range" value="' + idx + '"'
        + (idx === current ? " checked" : "") + '> ' + opt.label + '</label>';
    });
    html += '</div>';
    html += '<div class="cf-chart"></div>';
    html += '</div>';
    card.innerHTML = html;

    card.querySelector(".subtitle").textContent =
        "牌组「" + DATA.deck + "」每张卡片的平均用时。";

    card.querySelectorAll("input[type=radio]").forEach(function (input) {
      input.addEventListener("change", function () {
        current = parseInt(input.value, 10);
        renderChart(card);
      });
    });

    renderChart(card);
    return card;
  }

  function ensureCard() {
    var gc = document.querySelector('div[class*="graphs-container"]');
    if (!gc) return false;
    if (!gc.querySelector("#" + CARD_ID)) {
      // 追加到图表列表最后，不打乱原生图表的排列顺序
      gc.appendChild(buildCard());
    }
    return true;
  }

  var tries = 0;
  var poll = setInterval(function () {
    if (ensureCard()) {
      clearInterval(poll);
      setInterval(ensureCard, 2000);
    } else if (++tries > 60) {
      clearInterval(poll);
    }
  }, 500);
})();
