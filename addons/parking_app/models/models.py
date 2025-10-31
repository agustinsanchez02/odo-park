# En parking_app/models/models.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import math
import datetime

class ParkingTicket(models.Model):
    _name = 'parking.ticket'
    _description = 'Ticket de Estacionamiento'

    # --- Campos del Modelo ---
    
    x_plate_number = fields.Char(string='Patente', required=True)
    x_start_time = fields.Datetime(string='Hora de Entrada', default=fields.Datetime.now)
    x_end_time = fields.Datetime(string='Hora de Salida')
    
    x_state = fields.Selection([
        ('activo', 'Activo'),
        ('finalizado', 'Finalizado'),
        ('facturado', 'Facturado'), # Aún podemos usar 'facturado' si pagó en MP
    ], string='Estado', default='activo', required=True)

    # Campo calculado para la duración
    x_duration = fields.Float(string="Duración (Horas)", compute="_compute_duration")
    
    # Este campo es opcional ahora, puedes borrarlo si quieres
    x_invoice_id = fields.Many2one('account.move', string="Factura", readonly=True)

    
    # --- Funciones (Métodos) del Modelo ---

    @api.depends('x_start_time', 'x_end_time')
    def _compute_duration(self):
        """Calcula la duración en horas."""
        for ticket in self:
            if ticket.x_start_time and ticket.x_end_time:
                delta = ticket.x_end_time - ticket.x_start_time
                ticket.x_duration = delta.total_seconds() / 3600.0
            else:
                ticket.x_duration = 0.0
   