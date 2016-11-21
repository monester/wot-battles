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

refresh_clan = function () {
    $.get('/battles/', {
        clan_id: $('.timetable').data('clan-id')
    }, function (data) {
        var time_width = $('.timetable-time').outerWidth();
        var start_date = new Date(data['time_range'][0]);
        var end_date = new Date(data['time_range'][1]);
        var assaults = data['assaults'];
        var clan_id = $('.timetable').data('clan-id');

        // templates
        var time_template_clan = "<div class='timetable-time'><span style='float: right'>{{ time }}</span><br/>" +
            "{{title}}: <a href='http://ru.wargaming.net/clans/wot/{{clan.clan_id}}/'>{{ clan.tag }}</a><br>" +
            "{{WR}} / {{battles}} / {{elo}}</div>";
        var time_template_noclan = "<div class='timetable-time'><span style='float: right'>{{ time }}</span><br/>" +
            "{{title}}: planned</div>";

        var province_tmpl = "<div class='timetable-province'><strong><a href='https://ru.wargaming.net/globalmap/#province/{{province_id}}'>" +
            "{{server}} | {{ name }} | {{ arena_name }}</a></strong><p style='width: 400px; white-space: normal'>"+
            "</p></div>";

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
            newrow.append("<div class='timetable-time'>" + time.shortTime().substr(0, 5) + "</div>");
        }
        table.css('width', ((end_date - start_date) / (60*30*1000) + 1) * time_width);
        table.append($("<tr></tr>").append(newrow));

        // fill battle times
        for(var i in assaults) {
            var province_info = assaults[i]['province_info'];
            var battles = assaults[i]['battles'];

            var province = $(Mustache.render(province_tmpl, {
                server: province_info['server'],
                name: province_info['province_name'],
                province_id: province_info['province_id'],
                arena_name: province_info['arena_name'],
                clans: assaults[i]['clans'],
            }));

            var assault_datetime = new Date(battles[0]['planned_start_at']);
            var padding = ((assault_datetime - start_date) / 1800000) * time_width;
            newrow = $("<td class='timetable-row'></td>");
            newrow.css("padding-left", padding);

            var total_battles = battles.length;
            for(var t in battles) {
                var title;
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
                    newrow.append(Mustache.render(time_template_clan, {
                        title: title,
                        clan: clan,
                        time: time.shortTime(),
                        WR: clan['arena_stat']['wins_percent'],
                        elo: clan['elo_' + province_info['max_vehicle_level']],
                        battles: clan['arena_stat']['battles_count']
                    }));
                } else {
                    newrow.append(Mustache.render(time_template_noclan, {
                        title: title,
                        time: time.shortTime(),
                    }));
                }
            }
            console.log(province_info['prime_time'].substr(3,2));
            // if(province_info['prime_time'].substr(3,2) == 0) {
            //     newrow.css('backgroud-color', '#000');
            //     province.css('backgroud-color', '#000');
            // }
            // table.append($("<tr style='background-color: #0F0'></tr>").append(newrow));
            table.append($("<tr></tr>").append(newrow));
            provinces.append(province);
        }
    });
};

auto_refresh = 'Off';
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

$(function () {
    refresh_clan();
    enable_auto();
});
