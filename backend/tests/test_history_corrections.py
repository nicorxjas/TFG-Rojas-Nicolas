"""History transport and scope edits must preserve the user's latest meaning."""
import unittest

from services.conversation_context import select_conversation_history, scope_reset_request


class HistoryCorrectionTests(unittest.TestCase):
    def test_correction_survives_full_prefix_and_budget_pressure(self):
        original = {"role": "user", "content": ("El contexto inicial es X. " + "x" * 6000)[:6000]}
        correction = {"role": "user", "content": "Corrección: el contexto vigente es Y."}
        history = [original] + [{"role": "assistant", "content": "a" * 6000} for _ in range(7)]
        history += [correction] + [{"role": "user", "content": "b" * 6000} for _ in range(12)]
        selected = select_conversation_history(history)
        self.assertIn(correction, selected)
        self.assertLessEqual(sum(len(message["content"]) for message in selected), 48000)
        self.assertEqual(selected[-1], history[-1])
        self.assertEqual(select_conversation_history(selected), selected)

    def test_corrections_for_multiple_domains_survive(self):
        corrections = [
            {"role": "user", "content": "Corrijo: en salud contamos sesiones, no pacientes."},
            {"role": "user", "content": "En realidad el negocio industrial tiene dos plantas."},
        ]
        history = [{"role": "user", "content": "x" * 6000} for _ in range(8)]
        history += corrections + [{"role": "assistant", "content": "y" * 6000} for _ in range(10)]
        selected = select_conversation_history(history)
        for correction in corrections:
            self.assertIn(correction, selected)

    def test_long_message_keeps_head_and_final_correction_and_marks_gap(self):
        content = "Contexto inicial. " + "x" * 7000 + " Corrección final: el negocio ahora es Y."
        selected = select_conversation_history([{"role": "user", "content": content}])
        transmitted = selected[0]["content"]
        self.assertTrue(transmitted.startswith("Contexto inicial."))
        self.assertTrue(transmitted.endswith("Corrección final: el negocio ahora es Y."))
        self.assertIn("[Mensaje truncado:", transmitted)
        self.assertEqual(len(transmitted), 6000)
        self.assertEqual(select_conversation_history(selected), selected)

    def test_loading_errors_are_excluded_and_empty_scope_reset_is_retained(self):
        reset = {"role": "assistant", "content": "Listo.", "semantic_context": {
            "version": 3, "scope_reset": True, "query": {}, "selected_entities": []}}
        history = [
            {"role": "assistant", "content": "Parcial", "isLoading": True},
            {"role": "assistant", "content": "Error: servicio"}, reset,
        ] + [{"role": "assistant", "content": "x" * 6000} for _ in range(10)]
        selected = select_conversation_history(history)
        self.assertIn(reset, selected)
        self.assertFalse(any(message["content"] in {"Parcial", "Error: servicio"} for message in selected))
        self.assertEqual(selected[-1], history[-1])

    def test_state_only_reset_is_retained_with_opaque_keys_and_no_prose(self):
        previous = {"role": "assistant", "content": "Resultado anterior", "semantic_context": {
            "connection_id": "c", "query": {"measures": ["Q17.k03"],
                "filters": [{"member": "R21.k08", "operator": "equals", "values": ["A"]}]}}}
        reset = {"role": "assistant", "content": "", "semantic_context": {
            "version": 3, "scope_reset": True, "connection_id": "c", "query": {}, "selected_entities": []}}
        history = [previous, reset] + [{"role": "user", "content": "x" * 6000} for _ in range(12)]
        selected = select_conversation_history(history)
        self.assertIn(reset, selected)
        states = [message["semantic_context"] for message in selected if "semantic_context" in message]
        self.assertEqual(states[-1], reset["semantic_context"])
        self.assertLessEqual(sum(len(message["content"]) for message in selected), 48000)
        self.assertEqual(select_conversation_history(selected), selected)


class ScopeResetTests(unittest.TestCase):
    def test_partial_and_complete_resets(self):
        cases = [
            ("Olvidá solo el período anterior", (False, True, False)),
            ("Olvidá todo el período anterior", (False, True, False)),
            ("Quitá el filtro temporal", (False, True, False)),
            ("Retirá únicamente la restricción temporal", (False, True, False)),
            ("Olvidá exclusivamente el período del paciente anterior", (False, True, False)),
            ("Olvidá la máquina seleccionada en el período anterior", (True, False, False)),
            ("Sin filtro de fecha", (False, True, False)),
            ("Olvidá el cliente anterior", (True, False, False)),
            ("Retirá la entidad seleccionada", (True, False, False)),
            ("No uses los filtros anteriores", (True, False, False)),
            ("Olvidá el cliente y el período anteriores", (True, True, False)),
            ("Desde ahora hablamos del negocio completo", (True, False, False)),
            ("Ventas del negocio completo en todo el histórico", (True, True, False)),
            ("Quitá todos los filtros", (True, False, False)),
            ("Olvidá todo", (True, True, True)),
            ("Reiniciá la conversación", (True, True, True)),
            ("Nuevo chat", (True, True, True)),
            ("Olvidá todo salvo el período", (True, False, False)),
            ("Olvidá solo el cliente y conservá el período", (True, False, False)),
            ("Quitá el período, pero mantené el cliente", (False, True, False)),
        ]
        for prompt, flags in cases:
            with self.subTest(prompt=prompt):
                result = scope_reset_request(prompt)
                self.assertEqual(result, dict(zip(("reset_filters", "reset_period", "clear_all"), flags)))

    def test_reset_vocabulary_is_independent_of_business_domain(self):
        for entity in ("cliente", "producto", "proveedor", "canal", "segmento", "región", "entidad",
                       "paciente", "máquina", "departamento", "sucursal", "unidad asistencial"):
            with self.subTest(entity=entity):
                self.assertEqual(scope_reset_request(f"Olvidá el {entity} anterior"), {
                    "reset_filters": True, "reset_period": False, "clear_all": False})

    def test_arbitrary_selection_labels_and_opaque_keys_do_not_control_reset(self):
        for label, key in (("paciente", "Q17.k03"), ("máquina", "R21.k08"), ("departamento", "Z30.k11")):
            with self.subTest(label=label, key=key):
                messages = [{"role": "assistant", "content": "", "semantic_context": {
                    "query": {"measures": ["M00.k01"], "filters": [{"member": key, "values": ["A"]}]},
                    "selected_entities": [{"member": key, "value": "A"}]}}]
                self.assertEqual(select_conversation_history(messages), messages)
                self.assertEqual(scope_reset_request(f"Retirá el {label} seleccionado"), {
                    "reset_filters": True, "reset_period": False, "clear_all": False})
                self.assertEqual(scope_reset_request(f"Quitá solo el período y mantené el {label}"), {
                    "reset_filters": False, "reset_period": True, "clear_all": False})

    def test_global_scope_and_temporal_instructions_for_arbitrary_domains(self):
        for prompt in ("Quitá la selección de máquinas", "No tengas en cuenta el departamento elegido"):
            with self.subTest(prompt=prompt):
                self.assertEqual(scope_reset_request(prompt), {
                    "reset_filters": True, "reset_period": False, "clear_all": False})
        self.assertEqual(scope_reset_request("Olvidá solo el período; quiero consultar el monto de la máquina"), {
            "reset_filters": False, "reset_period": True, "clear_all": False})

    def test_all_values_for_one_field_does_not_clear_other_entity_filters(self):
        for prompt in (
            "Todos los rubros que compra ese cliente",
            "Mostrame todos los departamentos de ese paciente",
            "Ranking de todos los proveedores por monto",
            "¿Y la cantidad para todos los pacientes?",
            "Volvamos a todas las sucursales",
            "Ahora analizá todos los pacientes",
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(scope_reset_request(prompt))

    def test_regular_questions_and_negative_commands_are_not_resets(self):
        for prompt in (
            "¿Cuál es el monto del cliente anterior?", "¿Y en febrero de 2024?",
            "¿Qué significa sin filtro temporal?", "No olvides el cliente anterior",
            "No quites el período", "Mantené los filtros actuales", "¿Cómo se define el período?",
            "Olvidá la métrica anterior", "Quitá el indicador elegido", "Usá otro promedio",
            "¿Cuánto atendió el paciente anterior?", "Compará todos los meses de 2024",
        ):
            with self.subTest(prompt=prompt):
                self.assertIsNone(scope_reset_request(prompt))


if __name__ == "__main__":
    unittest.main()
