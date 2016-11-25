$('input').on('itemAdded', function(event) {
    $.post('/tag/',{
        'province_id': event.target.id,
        'tag': event.item,
        'date': event.target.getAttribute('data-date')
    });
}).on('itemRemoved', function(event) {
    $.ajax('/tag/',{
        'method': 'DELETE',
        'data': {
            'province_id': event.target.id,
            'tag': event.item,
            'date': event.target.getAttribute('data-date')
        }
    });
});

Date.prototype.addMinutes = function (min) {
    this.setTime(this.getTime() + (min*60*1000));
    return this;
};

Date.prototype.shortTime = function () {
    return this.toTimeString().substr(0,8);
};

var selected_date = 'latest';
refresh_clan = function (force_update) {
    force_update = force_update != undefined;
    console.log(selected_date);
    var url = '/battles/';
    if(selected_date != 'latest')
        url += selected_date + '/';

    $.get(url, {
        clan_id: $('.timetable').data('clan-id'),
        force_update: force_update
    }, function (data) {
        var time_width = $('.timetable-cell').outerWidth();
        var start_date = new Date(data['time_range'][0]);
        var end_date = new Date(data['time_range'][1]);
        var assaults = data['assaults'];
        var clan_id = $('.timetable').data('clan-id');

        // templates
        var time_template_clan = "<div class='timetable-time'><p><span style='float: right'>{{ time }}</span></p>" +
            "<p>{{title}}: <a href='http://ru.wargaming.net/clans/wot/{{clan.clan_id}}/'>{{ clan.tag }}</a></p>" +
            "<p class='stat-row'><span>{{WR}}</span><span>{{battles}}</span><span>{{elo}}</span></p></div>";
        var time_template_noclan = "<div class='timetable-time'><span style='float: right'>{{ time }}</span><br/>" +
            "{{title}}: planned</div>";

        var template = '<div class="timetable-cell">' +
            '<div class="timetable-cell-header"><span>{{round}}</span><span>{{time}}</span></div>' +
            '<div class="timetable-cell-opponent"><span>{{clan_tag}}</span></div>' +
            '<div class="timetable-cell-stats"><span>{{WR}}</span><span>{{battles}}</span><span>{{elo}}</span></div>' +
            '</div>';

        time_template_clan = template;
        time_template_noclan = template;
        var time_template_skipped = template;

        var province_tmpl = "<div class='timetable-province'><strong><a href='https://ru.wargaming.net/globalmap/#province/{{province_id}}'>" +
            "{{server}} | {{ name }} | {{ arena_name }} | {{ mode }}</a></strong></div>";

        Mustache.parse(time_template_clan);
        Mustache.parse(time_template_noclan);
        Mustache.parse(province_tmpl);

        // cleanup table
        $('.timetable-times table tr').remove();
        $('.timetable-provinces div').remove();

        // fill header line with times
        var table = $('.timetable-times table');
        var provinces = $('.timetable-provinces');
        var newrow = $( "<td class='timetable-row'></td>" );
        for(var time=new Date(start_date); time <= end_date; time=time.addMinutes(30)) {
            newrow.append("<div class='timetable-cell'>" + time.shortTime().substr(0, 5) + "</div>");
        }
        table.css('width', ((end_date - start_date) / (60*30*1000) + 1) * time_width);
        table.append($("<tr></tr>").append(newrow));

        // fill battle times
        for(var i=0; i<assaults.length; i++) {
            var province_info = assaults[i]['province_info'];
            var battles = assaults[i]['battles'];
            var mode = assaults[i]['mode'];
            var total_battles = battles.length;

            var province = $(Mustache.render(province_tmpl, {
                server: province_info['server'],
                name: province_info['province_name'],
                province_id: province_info['province_id'],
                arena_name: province_info['arena_name'],
                mode: mode,
                clans: assaults[i]['clans']
            }));

            var assault_datetime, padding;
            assault_datetime = new Date(battles[0]['planned_start_at']);
            padding = ((assault_datetime - start_date) / 1800000) * time_width;

            newrow = $("<td class='timetable-row'></td>");
            newrow.css("padding-left", padding);
            for(var t in battles) {
                var title, clan;
                var battle = battles[t];
                if(battle['real_start_at']) {
                    time = new Date(battle['real_start_at']);
                } else {
                    time = new Date(battle['planned_start_at']);
                }
                if(total_battles - t > 2) {
                    title = "1/" + Math.pow(2, total_battles - t - 2);
                } else if(total_battles - t == 2) {
                    title = "Final";
                } else {
                    title = "Owner";
                }
                if(battle['clan_a'] && battle['clan_b']) {
                    if(battle['clan_a']['clan_id'] == clan_id) {
                        clan = battle['clan_b'];
                    } else {
                        clan = battle['clan_a'];
                    }
                    console.log(clan['tag']);
                    newrow.append(Mustache.render(time_template_clan, {
                        round: title,
                        clan_tag: clan['tag'],
                        time: time.shortTime(),
                        WR: clan['arena_stat']['wins_percent'] + '%',
                        elo: clan['elo_' + province_info['max_vehicle_level']],
                        battles: clan['arena_stat']['battles_count']
                    }));
                } else {
                    if(battle['winner'] && battle['winner']['clan_id'] == clan_id) {
                        newrow.append(Mustache.render(time_template_skipped, {
                            round: title,
                            time: time.shortTime(),
                            clan_tag: 'SKIPPED'
                        }));
                    } else {
                        newrow.append(Mustache.render(time_template_noclan, {
                            round: title,
                            time: time.shortTime()
                        }));
                    }
                }
            }
            table.append($("<tr></tr>").append(newrow));
            provinces.append(province);
        }
    });
    last_updated = Date.now();
};

// Auto refresh switch
var auto_refresh = 'Off';
var interval;
enable_auto = function () {
    if (auto_refresh == 'Off') {
        interval = setInterval(refresh_clan, 30000);
        auto_refresh = 'On';
        document.getElementById('enable-auto').innerText = 'Auto-refresh: On';
    } else {
        clearInterval(interval);
        auto_refresh = 'Off';
        document.getElementById('enable-auto').innerText = 'Auto-refresh: Off';
    }
};

// select active date
$("#date-selector").find("a").click(function (e) {
    var menu_item = document.getElementById('selected-date');
    var ds = document.getElementById('date-selector');
    var items = ds.getElementsByTagName('li');
    for(var i=0; i<items.length; i++) {
        items[i].classList.remove('active')
    }
    this.parentNode.classList.add('active');
    selected_date = this.innerText;
    refresh_clan();
    menu_item.innerText = "Date: " + this.innerText;
});

// last updated
last_updated = "Never";
last_updated_function = function() {
    document.getElementById('last-updated').getElementsByTagName('span')[0].innerText =
        parseInt(Math.ceil((Date.now() - last_updated) / 1000)) + ' seconds ago';
};

// Auto start on load
$(function () {
    refresh_clan();
    enable_auto();
    setInterval(last_updated_function, 1000);
});
