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
// $(function () {
// var timetable = new Timetable();
// timetable.setScope(18, 3);
// timetable.addLocations(['Silent Disco', 'Nile', 'Len Room', 'Maas Room']);
// timetable.addEvent('1/8\nok', 'Nile', new Date(2015,7,17,19,0), new Date(2015,7,17,19,30));
// timetable.addEvent('1/4', 'Nile', new Date(2015,7,17,19,30), new Date(2015,7,17,20,0));
// timetable.addEvent('1/2', 'Nile', new Date(2015,7,17,20,0), new Date(2015,7,17,20,30));
// timetable.addEvent('Final', 'Nile', new Date(2015,7,17,20,30), new Date(2015,7,17,21,0));
// timetable.addEvent('Owner', 'Nile', new Date(2015,7,17,21,0), new Date(2015,7,17,21,30));
// var renderer = new Timetable.Renderer(timetable);
// renderer.draw('.timetable'); // any css selector
// });


// $(function () {
//     times = $('.timetable-times table');
//
//     for(i=0; i<5; i++) {
//         newtr =
//         newrow = $( "<td class='timetable-row'></td>" );
//         newrow.css('padding-left', 150 * i + 'px'  );
//         for(j=0; j<5; j++) {
//             time = $( "<div class='timetable-time'>some time</div>" );
//             newrow.append(time)
//         }
//         times.append($("<tr></tr>").append(newrow));
//     }
// });


Date.prototype.addMinutes = function (min) {
    this.setTime(this.getTime() + (min*60*1000));
    return this;
};

Date.prototype.shortTime = function () {
    return this.toTimeString().substr(0,8);
};

$.get('/battles/', function (data) {
    var time_width = $('.timetable-time').outerWidth();
    var start_date = new Date(data['time_range'][0]);
    var end_date = new Date(data['time_range'][1]);
    var assaults = data['assaults'];

    // templates
    var time_template = "<div class='timetable-time'><span style='float: right'>{{ time }}</span>" +
        "<br/>{{ clan_a }} VS {{ clan_b }}</div>";
    var province_tmpl = "<div class='timetable-province'><a href='https://ru.wargaming.net/globalmap/#province/{{province_id}}'>" +
        "{{server}} | {{ name }} | {{ arena_name }}</a><p style='width: 300px; white-space: normal'>{{#clans}}{{tag}}, {{/clans}}</p></div>";

    Mustache.parse(time_template);

    // cleanup table
    $('.timetable-times table tr').remove();
    $('.timetable-provinces div').remove();

    // fill header line with times
    var table = $('.timetable-times table');
    var provinces = $('.timetable-provinces');
    var newrow = $( "<td class='timetable-row'></td>" );
    for(var time=new Date(start_date); time <= end_date; time=time.addMinutes(30)) {
        newrow.append("<div class='timetable-time'>" + time.shortTime() + "</div>");
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

        for(t in battles) {
            var battle = battles[t];
            if(battle['real_start_at']) {
                time = new Date(battle['real_start_at']);
            } else {
                time = new Date(battle['planned_start_at']);
            }
            clan_a_tag = clan_b_tag = 'None';
            if(battle['clan_a'] && battle['clan_b']) {
                clan_a_tag = battle['clan_a']['tag'];
                clan_b_tag = battle['clan_b']['tag'];
            }
            console.log({clan_a: clan_a_tag, clan_b: clan_b_tag, time: time});
            newrow.append(Mustache.render(time_template, {
                clan_a: clan_a_tag,
                clan_b: clan_b_tag,
                time: time.shortTime()
            }));
        }
        table.append($("<tr></tr>").append(newrow));
    }
});
