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
