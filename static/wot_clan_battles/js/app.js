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

$.get('/battles/', {
    clan_id: $('.timetable').data('clan-id')
}, function (data) {
    var time_width = $('.timetable-time').outerWidth();
    var start_date = new Date(data['time_range'][0]);
    var end_date = new Date(data['time_range'][1]);
    var assaults = data['assaults'];
    var clan_id = $('.timetable').data('clan-id');

    // templates
    var time_template;
    var time_template_clan = "<div class='timetable-time'><span style='float: right'>{{ time }}</span>" +
        "<br/>{{title}}: <a href='http://ru.wargaming.net/clans/wot/{{clan.clan_id}}/'>{{ clan.tag }}</a></div>";
    var time_template_noclan = "<div class='timetable-time'><span style='float: right'>{{ time }}</span>" +
        "<br/>{{title}}: planned</div>";
    var province_tmpl = "<div class='timetable-province'><a href='https://ru.wargaming.net/globalmap/#province/{{province_id}}'>" +
        "{{server}} | {{ name }} | {{ arena_name }}</a><p style='width: 400px; white-space: normal'>"+
        "{{#clans}}<a href='http://ru.wargaming.net/clans/wot/{{clan_id}}/'>{{tag}}</a> {{/clans}}</p></div>";

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
    table.append($("<tr></tr>").append(newrow));

    // console.log(assaults);
    // fill battle times
    for(var i in assaults) {
        var province_info = assaults[i]['province_info'];
        var battles = assaults[i]['battles'];

        provinces.append(Mustache.render(province_tmpl, {
            server: province_info['server'],
            name: province_info['province_name'],
            province_id: province_info['province_id'],
            arena_name: province_info['arena_name'],
            clans: assaults[i]['clans'],
        }));

        var assault_datetime = new Date(battles[0]['planned_start_at']);
        padding = ((assault_datetime - start_date) / 1800000) * time_width;
        newrow = $("<td class='timetable-row'></td>");
        newrow.css("padding-left", padding);

        var total_battles = battles.length;
        for(var t in battles) {
            var battle = battles[t];
            if(battle['real_start_at']) {
                time = new Date(battle['real_start_at']);
            } else {
                time = new Date(battle['planned_start_at']);
            }
            var clan = {tag: ''};
            if(battle['clan_a'] && battle['clan_b']) {
                time_template = time_template_clan;
                if(battle['clan_a']['clan_id'] == clan_id) {
                    clan = battle['clan_b'];
                } else {
                    clan = battle['clan_a'];
                }
            } else {
                time_template = time_template_noclan;
            }
            var title;
            if(total_battles - t > 2) {
                title = "1/" + Math.pow(2, total_battles - t - 2);
            } else if(total_battles - t == 2) {
                title = "Final";
            } else {
                title = "Owner";
            }
            newrow.append(Mustache.render(time_template, {
                title: title,
                clan: clan,
                time: time.shortTime()
            }));
        }
        table.append($("<tr></tr>").append(newrow));
    }
});
