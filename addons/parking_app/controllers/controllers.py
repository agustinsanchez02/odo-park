# from odoo import http


# class ParkingApp(http.Controller):
#     @http.route('/parking_app/parking_app', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/parking_app/parking_app/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('parking_app.listing', {
#             'root': '/parking_app/parking_app',
#             'objects': http.request.env['parking_app.parking_app'].search([]),
#         })

#     @http.route('/parking_app/parking_app/objects/<model("parking_app.parking_app"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('parking_app.object', {
#             'object': obj
#         })

